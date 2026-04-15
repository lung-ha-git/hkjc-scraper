#!/usr/bin/env python3
"""
Post-ST-backfill task runner.
Polls process "grand-nexus" until backfill completes, then runs all post-backfill tasks.

Usage: python3 /app/src/post_backfill_tasks.py
"""
import subprocess
import time
import sys
import os

BACKFILL_SESSION = "grand-nexus"
HKJC_DIR = "/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC"

def run_cmd(cmd, desc, check=True):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    r = subprocess.run(cmd, shell=True)
    ok = r.returncode == 0
    if not ok and check:
        print(f"❌ FAILED: {desc}")
    else:
        print(f"✅ Done: {desc}")
    return ok

def main():
    # 0. Check if backfill already done
    result = subprocess.run(
        ["ps", "aux"], capture_output=True, text=True
    )
    if "backfill_st_historical" not in result.stdout:
        print("⚠️  Backfill may already be done or not running. Proceeding...")
    else:
        print("⏳ Backfill still running...")

    # 1. Wait up to 15 minutes for backfill to finish
    for i in range(90):
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        )
        if "backfill_st_historical" not in result.stdout:
            print(f"\n✅ Backfill done! ({i*10}s elapsed)")
            break
        if i % 6 == 0:
            print(f"  [{time.strftime('%H:%M:%S')}] waiting... ({i*10}s)", flush=True)
        time.sleep(10)
    else:
        print("⏰ Timeout waiting for backfill, proceeding anyway")

    time.sleep(2)

    # 2. Check final state
    print("\n📊 Final DB state (container):")
    subprocess.run("""docker exec hkjc-mongodb mongosh --quiet --username admin \
        --password 'CHANGE_ME_STRONG_PASSWORD_123!' --authenticationDatabase admin horse_racing \
        --eval '
        print("races: " + db.races.countDocuments({}) + " | ST: " + db.races.countDocuments({venue:"ST"}) + " | HV: " + db.races.countDocuments({venue:"HV"}));
        print("race_results: " + db.race_results.countDocuments({}));
        print("race_payouts: " + db.race_payouts.countDocuments({}));
        print("ML-ready: " + db.races.countDocuments({class:{$exists:true},results:{$exists:true,$ne:null}}));
        '""", shell=True)

    # 3. Dump container MongoDB
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_cmd(
        f"docker exec hkjc-mongodb mongodump --username admin "
        f"--password 'CHANGE_ME_STRONG_PASSWORD_123!' "
        f"--authenticationDatabase admin --db horse_racing "
        f"--out /dump/horse_racing_final_{ts}",
        "[1/7] Dump container MongoDB"
    )

    # 4. Stop Docker MongoDB, import to local
    print("\n🛑 Stopping Docker MongoDB...")
    subprocess.run("docker stop hkjc-mongodb", shell=True)
    time.sleep(5)

    # Use the new dump
    dump_dir_result = subprocess.run(
        "docker exec hkjc-mongodb ls -dt /dump/horse_racing_final_* 2>/dev/null | head -1",
        shell=True, capture_output=True, text=True
    )
    dump_dir = dump_dir_result.stdout.strip()
    print(f"   Using dump dir: {dump_dir}")

    # Copy dump to host
    host_dump = f"/tmp/{ts}"
    subprocess.run(f"docker cp hkjc-mongodb:{dump_dir} {host_dump}", shell=True)
    print(f"   Copied to {host_dump}")

    run_cmd(
        f"mongorestore --host localhost --nsInclude='horse_racing.*' {host_dump}/horse_racing/ --drop 2>&1",
        "[2/7] Restore to local MongoDB (replace horse_racing)"
    )

    # 5. Restart Docker MongoDB
    print("\n▶️  Restarting Docker MongoDB...")
    subprocess.run("docker start hkjc-mongodb", shell=True)
    time.sleep(3)
    run_cmd("docker exec hkjc-mongodb mongosh --quiet --username admin --password 'CHANGE_ME_STRONG_PASSWORD_123!' --authenticationDatabase admin horse_racing --eval 'print(\"Container DB back ✅ races:\", db.races.countDocuments({}))'", 
            "Verify container DB restored")

    # 6. Validate format
    print("\n[3/7] Validating races collection format...")
    subprocess.run("""mongosh --quiet --host localhost --eval '
var db = db.getMongo().getDB("horse_racing");

// HV sample
var hv = db.races.findOne({venue:"HV"});
print("=== HV race schema ===");
print("Keys:", Object.keys(hv).join(", "));
if (hv.results && hv.results[0]) {
    print("results[0].keys:", Object.keys(hv.results[0]).join(", "));
    print("  win_odds sample:", hv.results[0].win_odds);
}
if (hv.payout) {
    print("payout.keys:", Object.keys(hv.payout).join(", "));
}
print("payout.win sample:", hv.payout ? JSON.stringify(hv.payout.win) : "MISSING");

// ST sample  
var st_with_results = db.races.findOne({venue:"ST", race_results:{$exists:true,$ne:[]}});
if (st_with_results) {
    print("");
    print("=== ST race schema (with race_results) ===");
    print("Keys:", Object.keys(st_with_results).join(", "));
    if (st_with_results.race_results && st_with_results.race_results[0]) {
        print("race_results[0].keys:", Object.keys(st_with_results.race_results[0]).join(", "));
    }
} else {
    print("=== ST: No races with embedded race_results ===");
}

// race_payouts sample
var rp = db.race_payouts.findOne();
if (rp) {
    print("");
    print("=== race_payouts schema ===");
    print("Keys:", Object.keys(rp).join(", "));
    print("pools.win sample:", JSON.stringify(rp.pools.win));
}

// ML-ready count
print("");
var ml_hv = db.races.countDocuments({venue:"HV",class:{$exists:true},results:{$exists:true,$ne:null}});
var ml_st = db.races.countDocuments({venue:"ST",class:{$exists:true},race_results:{$exists:true,$ne:[]}});
print("ML-ready: HV=" + ml_hv + " ST=" + ml_st + " Total=" + (ml_hv+ml_st));
'""", shell=True)
    print("✅ [3/7] Format validation done")

    print("\n[4/7] ML Training — spawn sub-agent")
    print("[5/7] Commit source code — spawn sub-agent")
    print("[6/7] Update container model — spawn sub-agent")
    print("[7/7] Webapp check — spawn sub-agent")

    print("\n✅ All immediate tasks complete!")

if __name__ == "__main__":
    main()

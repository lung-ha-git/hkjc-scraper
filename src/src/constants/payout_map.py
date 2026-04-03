# Pool name mapping: Chinese (HTML) → English (standardized)
POOL_NAME_MAP = {
    "獨贏": "win",
    "位置": "place",
    "連贏": "quinella",
    "位置Q": "quinella_place",
    "二重彩": "double",
    "三重彩": "treble",
    "單T": "trio",
    "四連環": "first_4",
    "四重彩": "quartet",
    # 孖寶 (doubles per race leg)
    "第一口孖寶": "double_1",
    "第二口孖寶": "double_2",
    "第三口孖寶": "double_3",
    "第四口孖寶": "double_4",
    "第五口孖寶": "double_5",
    "第六口孖寶": "double_6",
    "第七口孖寶": "double_7",
    "第八口孖寶": "double_8",
    "第九口孖寶": "double_9",
    "第十口孖寶": "double_10",
    # 孖T (quinella tier per race leg)
    "第一口孖T": "quinella_trio_1",
    "第二口孖T": "quinella_trio_2",
    "第三口孖T": "quinella_trio_3",
    "第四口孖T": "quinella_trio_4",
    "第五口孖T": "quinella_trio_5",
    "第六口孖T": "quinella_trio_6",
    "第七口孖T": "quinella_trio_7",
    "第八口孖T": "quinella_trio_8",
    "第九口孖T": "quinella_trio_9",
    "第十口孖T": "quinella_trio_10",
    # 三寶 (treble per race leg)
    "第一口三寶": "treble_1",
    "第二口三寶": "treble_2",
    "第三口三寶": "treble_3",
    "第四口三寶": "treble_4",
    "第五口三寶": "treble_5",
    "第六口三寶": "treble_6",
    "第七口三寶": "treble_7",
    "第八口三寶": "treble_8",
    "第九口三寶": "treble_9",
    "第十口三寶": "treble_10",
    # T3 jackpot
    "三T": "t3_jackpot",
    "三T(安慰獎)": "t3_consolation",
    # 六環彩
    "六環彩": "six_ring",
    # 騎師王/練馬師王
    "騎師王 1": "jockey_win",
    "練馬師王 1": "trainer_win",
    # Other
    "彩池": "pool_info",
}

def normalize_payout_keys(payouts: dict) -> dict:
    """Convert Chinese payout keys to English."""
    if not isinstance(payouts, dict):
        return payouts
    result = {}
    for cn_key, value in payouts.items():
        en_key = POOL_NAME_MAP.get(cn_key, cn_key)
        result[en_key] = value
    return result

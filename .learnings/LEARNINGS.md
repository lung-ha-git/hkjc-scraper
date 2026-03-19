# Learnings

## [LRN-20260319-001] MongoDB field names are case-sensitive

**Logged**: 2026-03-19T04:14:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
MongoDB field names are case-sensitive. Querying `{'Name': None}` (uppercase) instead of `{'name': None}` (lowercase) matches ALL documents because the field doesn't exist, not just those where name is null.

### Details
- Wrote Python script to add horses with `name=None` to scrape queue
- Used query `{'Name': None}` with uppercase 'Name'
- MongoDB treated non-existent field as matching all documents
- Result: 1186 horses with actual names were incorrectly added to queue

### Suggested Action
When querying MongoDB:
1. Always verify field names by checking a sample document first: `list(collection.find_one().keys())`
2. Field names in MongoDB are case-sensitive
3. Use `$exists: True` combined with `$ne: None` to be explicit about what you're looking for

### Metadata
- Source: error
- Related Files: hkjc_project/src/database/...
- Tags: mongodb, python, query-bug
- Pattern-Key: database.field_case_sensitivity

---

## [LRN-20260319-002] async context manager - class must implement __aenter__/__aexit__

**Logged**: 2026-03-19T03:30:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Using `async with SomeClass` requires the class to implement `__aenter__` and `__aexit__` methods. Regular `__enter__`/`__exit__` does not work.

### Details
- `CompleteHorseScraper` was a regular class with `__init__`
- Tried to use `async with CompleteHorseScraper(...)` in deep_sync.py
- Got error: `__aenter__`
- Fix: Remove `async with` and just instantiate the class directly

### Suggested Action
- Only use `async with` on classes that are async context managers (define `__aenter__` and `__aexit__`)
- Regular classes should be instantiated normally, not with `async with`

### Metadata
- Source: error
- Related Files: hkjc_project/src/pipeline/deep_sync.py, hkjc_project/src/crawler/complete_horse_scraper.py
- Tags: python, async, context-manager

---

## [LRN-20260319-003] MongoDB _id is immutable - remove before upsert

**Logged**: 2026-03-19T03:45:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
MongoDB `_id` field is immutable and cannot be updated. When upserting documents that may contain `_id` from scraped data, must remove it before `$set`.

### Details
- Scraper returned documents with `_id` field included
- Attempted to upsert to MongoDB with `$set: race_doc`
- Error: "Performing an update on the path '_id' would modify the immutable field '_id'"
- Fix: Create helper to filter out `_id` before upserting

### Suggested Action
When upserting scraped data to MongoDB:
```python
def clean_doc(doc):
    return {k: v for k, v in doc.items() if k != '_id'}

db.collection.update_one(query, {"$set": clean_doc(doc)}, upsert=True)
```

### Metadata
- Source: error
- Related Files: hkjc_project/src/pipeline/deep_sync.py
- Tags: mongodb, upsert, immutable

---

## [LRN-20260319-004] Python indentation bug - code after return never executes

**Logged**: 2026-03-19T03:35:00Z
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
Code placed after `return False` with same indentation was unreachable. This caused all database save operations to be skipped, but jobs were still marked as "completed" in queue.

### Details
- In deep_sync.py, `if not result: return False` was followed by db operations at same indentation level
- These lines were INSIDE the `if` block and never executed
- Jobs were marked completed but horses had no data saved

### Suggested Action
Always check indentation carefully after early returns:
```python
if not result:
    return False

# This code is at correct indentation level (outside the if block)
db.connect()
```

### Metadata
- Source: error
- Related Files: hkjc_project/src/pipeline/deep_sync.py
- Tags: python, indentation, bug

---

## [LRN-20260319-005] Horse name in <title> not <h1>

**Logged**: 2026-03-19T04:10:00Z
**Priority**: medium
**Status**: resolved
**Area**: crawler

### Summary
HKJC horse pages don't have horse name in `<h1>` tag. Name is in `<title>` tag (e.g., "榮耀盛甲 - 馬匹資料 - 香港賽馬會").

### Details
- complete_horse_scraper.py looked for name in `<h1>` tag
- `<h1>` doesn't exist on HKJC horse pages
- Horse name is in page title, extracted correctly but stored as None

### Suggested Action
When scraping HKJC pages, check both `<title>` and `<h1>` for content:
```python
# Horse name from title tag
title_match = re.search(r'<title[^>]*>([^<]+)', content)
if title_match:
    name = title_match.group(1).split(' - ')[0]
```

### Metadata
- Source: error
- Related Files: hkjc_project/src/crawler/complete_horse_scraper.py
- Tags: hkjc, scraping, html-parsing

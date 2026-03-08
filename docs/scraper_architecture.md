# HKJC Scraper Architecture - Phase 3

## Overview
Parallel scraping workflow with activity logging for full data collection.

## Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: Queue Initialization                               │
│  - Accept list of horse IDs                                  │
│  - Create queue entries in MongoDB                           │
│  - Skip already queued horses                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: Parallel Horse Scraping                            │
│  - Scrape max_concurrent horses simultaneously               │
│  - Extract race URLs from each horse's race_history          │
│  - Deduplicate race URLs using dict                          │
│  - Log all activities                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: Parallel Race Scraping                             │
│  - Queue all unique race URLs                                │
│  - Scrape max_concurrent races simultaneously                │
│  - Save results to: races, race_results, race_payouts        │
│  - Log all activities                                        │
└─────────────────────────────────────────────────────────────┘
```

## Collections

### scraper_queue
Tracks scraping jobs status.
```json
{
  "type": "horse|race",
  "id": "HK_2023_J256",
  "status": "pending|processing|done|error",
  "priority": 1,
  "created_at": "...",
  "updated_at": "...",
  "error": "..."  // only if status=error
}
```

### scraping_activity_log
Detailed log of all scraping operations.
```json
{
  "timestamp": "...",
  "phase": "phase1|phase2|phase3",
  "action": "queue_horse|scrape_horse|scrape_race",
  "target_id": "HK_2023_J256",
  "status": "success|error|skipped",
  "details": {...},
  "error_message": "..."
}
```

### race_urls (in-memory during run)
Temporary tracking of discovered races.
```json
{
  "race_id": "2026-03-01_7",
  "source_horses": ["HK_2023_J256", "HK_2020_E486"],
  "date": "2026/03/01",
  "extracted_from": "HK_2023_J256"
}
```

## Configuration

```python
scraper = OverallScraper(
    max_concurrent=3,  # Limit concurrent browser instances
    headless=True      # Run browser headlessly
)
```

## Activity Logging

All operations are logged:
- Queue operations (add, skip)
- Scraping attempts (start, success, error)
- Race URL discoveries

Logs available in MongoDB `scraping_activity_log` collection.

## Error Handling

- Failed operations retried (not implemented yet)
- Errors logged with full traceback
- Queue status updated to "error"
- Process continues with other items

## Future Enhancements

1. Retry logic for failed operations
2. Resume from checkpoint
3. Incremental updates (only new races)
4. Rate limiting
5. Proxy rotation

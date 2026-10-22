# Follow a request from API to dashboard

Request `70255923` is our original lesson example, inside the full creation cohort.

1. Python sends an HTTPS GET to NYC. The API returns JSON with an ID, opening time and closing time.
2. The Databricks raw table preserves the JSON, batch ID and checksum. This records what the API actually returned.
3. SQL parses the JSON and validates status and dates. This request opened at 00:00:05 and closed at 00:28:25. The duration is 1,700 seconds / 3,600 = about 0.4722 source wall-clock hours.
4. Reporting counts one request and includes its valid duration in its category average. Missing durations stay null, not zero.
5. Tableau reads one row per request from the saved extract. Selecting an agency narrows the rows contributing to the charts. It does not change Databricks or call the API again. The header explicitly shows static full-cohort baseline totals.

The workbook describes the saved extraction, not the current city workload. Closed does not prove customer satisfaction.

Practice: explain why a request with no closing date should not contribute zero hours to the average. This walkthrough supports learning; it does not establish independent mastery.

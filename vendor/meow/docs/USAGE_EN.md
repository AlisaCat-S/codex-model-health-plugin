# Usage and troubleshooting

Running detections are blue and show live scores. Completed, stopped or timed-out runs retain partial reports. Eligibility requires at least60% valid answers overall and per enabled cell. With new baselines, only the unique highest candidate can strictly cross its own line. Scores are not identity probabilities and need not sum to100%; incomplete sample sets may be less reliable.

Processed counts logical requests; valid samples count usable fingerprint answers; attempts include retries. The default whole-run retry budget is half the planned requests, rounded up. First attempts finish before rotating failed jobs. Exhausting retries does not hide partial results.

Errors retain upstream status, type, code and message, with sensitive information removed and text bounded. HTTP success and an in-stream error are separate. DNS/TLS/timeouts are not fabricated upstream messages. Missing old error bodies cannot be reconstructed.

If model discovery is unsupported, type the alias manually. Changing the URL/key invalidates the old list. Imported/default baselines affect new detections, not frozen reports or scheduled configurations. Closing the page does not stop a running local backend or its schedules.

Export a report for diagnosis. Request/response retention is explicit and local; review retained evidence before sharing it. The public website exposes only selected report fields.

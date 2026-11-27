# backfill last run

- at: 2026-11-27T18:17:09+08:00

- mode: auto
- crash: NameError: name 'os' is not defined
- traceback_tail:   File "/home/runner/work/jiucaiquan/jiucaiquan/services/market-data/backfill_gap.py", line 340, in run
    emit_has_gap(pending)
  File "/home/runner/work/jiucaiquan/jiucaiquan/services/market-data/backfill_gap.py", line 50, in emit_has_gap
    output_path = os.environ.get("GITHUB_OUTPUT")
                  ^^
NameError: name 'os' is not defined

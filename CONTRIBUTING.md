# Contributing to smart-city-gis

Thanks for taking the time to contribute. This project is a research-grade
urban analytics library, so contributions that keep results **reproducible**
are the most valuable.

## Quick start

```bash
git clone https://github.com/DongsooJung/smart-city-gis.git
cd smart-city-gis
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest tests/ -v
ruff check src tests
```

## Contribution flow

1. **Open an issue first** for anything larger than a bug fix, so the approach
   can be agreed on before you write code.
2. **Branch** from `main`: `git checkout -b feat/<short-topic>`.
3. **Keep the public API typed and tested.** Every behavioural change needs a
   test in `tests/`. Tests run on Python 3.11 and 3.12.
4. **Match the existing style.** The linter is `ruff` (default rules plus
   `I`, `UP`, `B`, `RUF`, `SIM`). Run `ruff check src tests` before pushing —
   CI enforces it.
5. **Open a PR** and describe what changed and why. Reference the issue.

## What the maintainer cares about

- **Honest scope.** If a function is a stub or an approximation, say so in the
  docstring and in the "구현 현황" table in `README.md`. Do not present an
  approximation as a validated result.
- **No silent data assumptions.** Coordinate systems (EPSG:5186 for metric
  distance), distance methods (straight-line vs. network), and collection
  windows must be stated in code and documentation.
- **Reproducibility.** Scripts under `scripts/` must write their outputs and
  the metadata needed to rebuild them (timestamps, source queries, hashes).

## Reporting bugs

Open an issue with the version, the exact command, the expected result, and
the actual result. If the issue contains a data or security concern, follow
`SECURITY.md` instead of the public issue tracker.

## License

Contributions are accepted under the [MIT License](LICENSE).

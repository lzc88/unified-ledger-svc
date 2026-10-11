import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from integrations.base import FormatError, IntegrationError, MappingResult

from .adapter import IbkrAdapter


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(
        prog="python -m integrations.ibkr",
        description="Fetch IBKR activity via Flex and write it into the ledger tables.",
    )
    parser.add_argument("--user", help="user_id that owns the imported accounts")
    parser.add_argument(
        "--from",
        dest="start",
        type=date.fromisoformat,
        default=yesterday - timedelta(days=364),
        help="first date, YYYY-MM-DD (default: 365 days ago)",
    )
    parser.add_argument(
        "--to",
        dest="end",
        type=date.fromisoformat,
        default=yesterday,
        help="last date, YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        nargs="+",
        help="map saved Flex XML file(s) instead of calling the API",
    )
    parser.add_argument(
        "--save-xml",
        type=Path,
        metavar="DIR",
        help="also save each fetched statement into DIR",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="map and report counts without writing to the database",
    )
    args = parser.parse_args(argv)
    if not args.dry_run and not args.user:
        parser.error("--user is required unless --dry-run is given")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    adapter = IbkrAdapter()
    try:
        if args.file:
            documents = [path.read_bytes() for path in args.file]
        else:
            documents = adapter.fetch(args.start, args.end)
            if args.save_xml:
                args.save_xml.mkdir(parents=True, exist_ok=True)
                for i, document in enumerate(documents, start=1):
                    (
                        args.save_xml / f"flex_{args.start}_{args.end}_{i}.xml"
                    ).write_bytes(document)
        result = adapter.map(documents)
    except (IntegrationError, FormatError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _report("mapped", _mapped_counts(result))
    else:
        from database.db import SessionLocal
        from integrations.load import known_broker_assets, load
        from integrations.openfigi import assign_figis, client_from_settings

        with SessionLocal() as session:
            known = known_broker_assets(session, adapter.broker_id, result.assets)
        try:
            assign_figis(result, known, client_from_settings())
        except IntegrationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        with SessionLocal.begin() as session:
            _report("inserted", load(session, adapter, result, args.user))

    print(f"{len(result.skipped)} skipped", file=sys.stderr)
    for row in result.skipped:
        print(
            f"  skipped {row.section} {row.transaction_id or '-'}: {row.reason}",
            file=sys.stderr,
        )
    return 0


def _mapped_counts(result: MappingResult) -> dict[str, int]:
    return {
        name: len(getattr(result, name))
        for name in (
            "assets",
            "accounts",
            "cash",
            "trade_orders",
            "trades",
            "trade_fees",
            "fx_pairs",
            "fx_orders",
            "fx",
            "fx_fees",
        )
    }


def _report(verb: str, counts: dict[str, int]) -> None:
    summary = ", ".join(f"{table} {count}" for table, count in counts.items())
    print(f"{verb}: {summary}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

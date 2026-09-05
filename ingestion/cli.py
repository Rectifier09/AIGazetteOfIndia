import argparse
import logging
from config import get_connection
from discovery import discover_and_ingest, MINISTRY_LABOUR_AND_EMPLOYMENT


def main():
    parser = argparse.ArgumentParser(
        description="Standalone e-Gazette ingestion pipeline. Runs independently of the "
                     "Query API and frontend — safe to start now and leave running while "
                     "those are built."
    )
    parser.add_argument("--ministry", default=MINISTRY_LABOUR_AND_EMPLOYMENT,
                         help="Ministry dropdown value (default: 28, Labour and Employment)")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = get_connection()
    logging.info(f"Starting ingestion: ministry={args.ministry} years={args.start_year}-{args.end_year}")
    count = discover_and_ingest(conn, args.ministry, args.start_year, args.end_year)
    logging.info(f"Done. Ingested {count} notifications total.")


if __name__ == "__main__":
    main()

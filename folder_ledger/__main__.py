"""Command-line entry point."""
import argparse
import sys

from .reports import write_report
from .scan import scan


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only folder inventory and duplicate reports')
    parser.add_argument('root', help='Directory to inventory; links are skipped')
    parser.add_argument('--exclude', action='append', default=[], metavar='GLOB')
    parser.add_argument('--hashes', action='store_true', help='Hash every regular file')
    parser.add_argument('--duplicates', action='store_true', help='Find equal-content file groups')
    parser.add_argument('--output', help='Report path outside the scanned tree')
    parser.add_argument('--format', choices=('json', 'csv'), default='json')
    parser.add_argument('--force', action='store_true', help='Replace an existing report')
    args = parser.parse_args(argv)
    if args.force and not args.output:
        parser.error('--force requires --output')
    try:
        result = scan(args.root, excludes=args.exclude, hashes=args.hashes,
                      duplicates=args.duplicates)
        if args.output:
            write_report(result, args.root, args.output, args.format, args.force)
    except (ValueError, OSError) as exc:
        print('folder-ledger: ' + str(exc), file=sys.stderr)
        return 2
    print(f"{len(result['files'])} files, {sum(f['size'] for f in result['files'])} bytes, "
          f"{len(result['duplicates'])} duplicate groups, {len(result['skipped'])} skipped, "
          f"{len(result['errors'])} errors")
    for error in result['errors']:
        # ascii keeps arbitrary filesystem names printable on legacy consoles.
        print(f"{ascii(error['path'])}: {ascii(error['error'])}", file=sys.stderr)
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

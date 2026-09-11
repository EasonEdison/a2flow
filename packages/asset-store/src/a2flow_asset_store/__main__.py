"""Operator-only CLI: offline validate, explicit setup, dry-run, then apply."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

from . import AssetError, PostgresAssetRepository
from .records import MAX_BYTES, canonical


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "setup", "dry-run", "apply"))
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--environment", choices=("PRT", "ONLINE"), required=True)
    parser.add_argument("--database")
    parser.add_argument("--dsn-env", help="name of host environment variable; never the DSN itself")
    parser.add_argument("--validator-factory", required=True, help="trusted operator module:function")
    parser.add_argument("--bundle")
    args = parser.parse_args(argv)
    try:
        module, name = args.validator_factory.split(":")
        validator = getattr(importlib.import_module(module), name)()
        document = None
        if args.command != "setup":
            if not args.bundle:
                raise AssetError("BUNDLE_REQUIRED")
            with Path(args.bundle).open("rb") as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise AssetError("BUNDLE_TOO_LARGE")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise AssetError("DUPLICATE_JSON_KEY")
                    result[key] = value
                return result
            document = json.loads(raw, object_pairs_hook=unique)
            validator.validate(document, expected_namespace=args.namespace,
                               expected_environment=args.environment)
        if args.command == "validate":
            result = {"status": "VALID", "namespace": args.namespace, "environment": args.environment}
        else:
            if not args.database or not args.dsn_env or not os.environ.get(args.dsn_env):
                raise AssetError("EXPLICIT_DESTINATION_REQUIRED")
            repository = PostgresAssetRepository(
                os.environ[args.dsn_env], environment=args.environment, database=args.database,
                validator=validator)
            if args.command == "setup":
                from .validation import namespace
                namespace(args.namespace)
                repository.setup()
                result = {"status": "SCHEMA_INITIALIZED", "environment": args.environment}
            else:
                result = repository.import_bundle(document, expected_namespace=args.namespace,
                                                   dry_run=args.command == "dry-run")
        print(canonical(result).decode("utf-8"))
        return 0
    except AssetError as error:
        print(json.dumps({"error": error.code}), file=sys.stderr)
        return 1
    except Exception:
        print('{"error":"OPERATOR_INPUT_OR_VALIDATION_FAILED"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

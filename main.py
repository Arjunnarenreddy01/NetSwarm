import argparse

def start_node():
    print("Starting node...")

def list_peers():
    print("Listing peers...")

def main():
    parser = argparse.ArgumentParser(description="NetSwarm CLI")
    subparsers = parser.add_subparsers(dest="command")

    # start-node command
    parser_start = subparsers.add_parser("start-node", help="Start the P2P node")
    parser_start.set_defaults(func=start_node)

    # list-peers command
    parser_list = subparsers.add_parser("list-peers", help="List known peers")
    parser_list.set_defaults(func=list_peers)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

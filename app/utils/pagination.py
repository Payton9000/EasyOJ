def parse_pagination(args, default_per_page=20, max_per_page=100):
    def read_int(name, default):
        try:
            return int(args.get(name, default))
        except (TypeError, ValueError):
            return default

    page = max(1, read_int('page', 1))
    per_page = min(max(1, read_int('per_page', default_per_page)), max_per_page)
    return page, per_page

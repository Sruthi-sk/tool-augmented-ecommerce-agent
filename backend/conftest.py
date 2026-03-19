"""Root conftest — skip integration tests unless explicitly requested."""


def pytest_collection_modifyitems(config, items):
    # If -m was passed explicitly, don't filter anything
    if config.getoption("-m"):
        return
    skip_integration = __import__("pytest").mark.skip(reason="needs -m integration")
    skip_live = __import__("pytest").mark.skip(reason="needs -m live")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
        if "live" in item.keywords:
            item.add_marker(skip_live)

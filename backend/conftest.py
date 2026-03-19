"""Root conftest — skip integration tests unless explicitly requested."""


def pytest_collection_modifyitems(config, items):
    # If -m "integration" was passed, don't filter anything
    if config.getoption("-m"):
        return
    skip = __import__("pytest").mark.skip(reason="needs --m integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)

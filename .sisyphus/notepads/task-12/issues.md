## Task 12

- `unittest.mock.MagicMock` is not pickle-friendly in this setup, so the pickle roundtrip test uses a top-level pickleable store double while other hook-routing tests continue to use `MagicMock`.

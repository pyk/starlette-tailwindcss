# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Removed

- Renamed the public installer helper from `download_binary` to `install`.

## [0.1.0] - 2026-04-03

### Added

- Starlette integration for running the Tailwind CSS CLI during application
  startup and watch mode.
- Support for using an existing Tailwind CSS binary via `bin_path`.
- Automatic Tailwind CSS binary installation when `version` is provided.
- Platform-aware binary resolution and cache management for auto-installed
  binaries.
- Optional `cache_dir` for controlling where auto-installed binaries are stored.
- Checksum verification for downloaded Tailwind CSS release binaries.
- Logging for Tailwind CSS build output and auto-install progress.
- Integration tests and example app coverage for local binary resolution,
  auto-install failure handling, cache reuse, and installer logging.

[Unreleased]: https://github.com/pyk/starlette-tailwindcss/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pyk/starlette-tailwindcss/releases/tag/v0.1.0

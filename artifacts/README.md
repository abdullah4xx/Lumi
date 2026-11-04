# Generated artifacts

- `releases/<version>/` contains locally built Debian, AppImage, and build
  metadata for that application version.
- `source/` contains manually prepared source archives.

Generated installers and source archives are ignored by Git. GitHub Actions
stores release binaries in GitHub Releases and workflow artifacts instead.

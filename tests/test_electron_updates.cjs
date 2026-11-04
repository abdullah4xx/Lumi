const assert = require('node:assert/strict');
const test = require('node:test');

const { getLatestRelease, isNewerVersion } = require('../electron/github-updates.cjs');

test('compares stable release versions numerically', () => {
  assert.equal(isNewerVersion('v1.14.6', '1.14.5'), true);
  assert.equal(isNewerVersion('1.14.4', '1.14.5'), false);
  assert.equal(isNewerVersion('1.14.5.0', '1.14.5'), false);
  assert.equal(isNewerVersion('1.15', '1.14.99'), true);
});

test('reads the latest release and Debian download from GitHub', async () => {
  let request;
  const release = await getLatestRelease(async (url, options) => {
    request = { url, options };
    return {
      ok: true,
      json: async () => ({
        tag_name: 'v1.14.6',
        html_url: 'https://github.com/abdullah4xx/Lumi/releases/tag/v1.14.6',
        assets: [{
          name: 'lumi-desktop_1.14.6_amd64.deb',
          browser_download_url: 'https://github.com/abdullah4xx/Lumi/releases/download/v1.14.6/lumi-desktop_1.14.6_amd64.deb',
        }],
      }),
    };
  });

  assert.equal(release.version, '1.14.6');
  assert.equal(release.debUrl.endsWith('.deb'), true);
  assert.equal(request.url, 'https://api.github.com/repos/abdullah4xx/Lumi/releases/latest');
  assert.equal(request.options.headers.Accept, 'application/vnd.github+json');
});

test('rejects failed GitHub release requests and untrusted package links', async () => {
  await assert.rejects(
    getLatestRelease(async () => ({ ok: false, status: 503 })),
    /HTTP 503/,
  );
  await assert.rejects(
    getLatestRelease(async () => ({
      ok: true,
      json: async () => ({
        tag_name: 'v1.14.6',
        assets: [{ name: 'lumi.deb', browser_download_url: 'https://example.com/lumi.deb' }],
      }),
    })),
    /untrusted Debian package URL/,
  );
});

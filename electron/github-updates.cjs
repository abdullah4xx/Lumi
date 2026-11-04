const RELEASES_API = 'https://api.github.com/repos/abdullah4xx/Lumi/releases/latest';

function versionParts(value) {
  const match = /^v?(\d+(?:\.\d+)*)$/.exec(String(value || ''));
  if (!match) throw new Error(`Unsupported Lumi release version: ${value}`);
  return match[1].split('.').map(Number);
}

function isNewerVersion(candidate, current) {
  const candidateParts = versionParts(candidate);
  const currentParts = versionParts(current);
  const length = Math.max(candidateParts.length, currentParts.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (candidateParts[index] || 0) - (currentParts[index] || 0);
    if (difference !== 0) return difference > 0;
  }
  return false;
}

async function getLatestRelease(fetchImpl = fetch) {
  const response = await fetchImpl(RELEASES_API, {
    headers: {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`GitHub Releases returned HTTP ${response.status}`);

  const release = await response.json();
  const version = String(release.tag_name || '').replace(/^v/, '');
  versionParts(version);
  const debAsset = Array.isArray(release.assets)
    ? release.assets.find(asset => String(asset.name || '').endsWith('.deb'))
    : null;
  const downloadUrl = debAsset?.browser_download_url || '';
  if (downloadUrl) {
    const url = new URL(downloadUrl);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com') {
      throw new Error('GitHub release contains an untrusted Debian package URL');
    }
  }

  return {
    version,
    releaseUrl: String(release.html_url || 'https://github.com/abdullah4xx/Lumi/releases/latest'),
    debUrl: downloadUrl,
  };
}

module.exports = { getLatestRelease, isNewerVersion };

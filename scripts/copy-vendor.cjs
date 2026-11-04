const fs = require('node:fs');
const path = require('node:path');

const source = path.resolve(__dirname, '../node_modules/gsap/dist/gsap.min.js');
const destination = path.resolve(__dirname, '../ui/vendor/gsap.min.js');

if (!fs.existsSync(source)) {
  console.error('GSAP is missing. Run npm install before starting or packaging Lumi.');
  process.exit(1);
}
fs.mkdirSync(path.dirname(destination), { recursive: true });
fs.copyFileSync(source, destination);

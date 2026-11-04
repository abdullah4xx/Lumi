# Lumi Icon Studio

Run `python3 tools/icon-studio/server.py` from the project root, then open
<http://127.0.0.1:5187>. The editor lets you adjust the center and edge proportions,
choose a background color, and use either a solid mark color or a three-color gradient.
The wallpaper preset adds the sampled olive, bronze, and warm-stone colors from the
reference image; its colors and gradient angle remain editable.
It can download SVG/PNG previews or apply the design to Lumi's icon source assets.

The server binds to loopback only. Applying a design updates the SVG, PNG, and Linux
icon-size assets in the project and the current user's `hicolor` launcher icons, then
refreshes the user's icon cache when `gtk-update-icon-cache` is available. It does not
rebuild or install the application, so changing the installed package's bundled window
icon still requires rebuilding and reinstalling Lumi. Exports also leave a visible
save link as a fallback if the browser blocks an automatic download. The icon artwork
keeps its existing band curves; only the outer image corners are rounded.

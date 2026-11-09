# Installing the new profile (5 minutes, all in the browser)

Your profile README lives in the repo named **exactly like your username**:
**https://github.com/Venu2328/Venu2328**. (ChatGPT's notes said a repo called `README` — that one would never show on your profile.)

## 1 · Clean up the old files
In `Venu2328/Venu2328`, delete the folder **`github/`** (no dot). The workflow inside it never ran — GitHub only runs workflows from `.github/workflows/` — which is why the snake image on your current profile is broken.

## 2 · Upload the new files
**Add file → Upload files**, then drag in, from this zip:
- `README.md` (replaces the old one)
- the whole `assets/` folder
- the whole `tools/` folder (optional, but it's how you edit the design later)

Commit straight to `main`.

## 3 · Turn on the contribution snake
**Add file → Create new file**, type the name `.github/workflows/snake.yml` (the slashes create the folders), paste in the contents of `.github/workflows/snake.yml` from this zip, and commit.

It runs immediately. After about a minute, the **Actions** tab shows a green tick and a new `output` branch exists. If it fails with a permissions error, go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, save, and re-run it.

> The `.github` folder is hidden on macOS (press <kbd>Cmd</kbd> + <kbd>Shift</kbd> + <kbd>.</kbd> in Finder to see it), which is why step 3 tells you to create the file instead of uploading it.

## 4 · Check it
Open https://github.com/Venu2328 and hard-refresh. GitHub caches images, so animations can take a minute to update.

---

## Editing later
All text, colours and links are in one place: the config block at the top of `tools/build_assets.py`.

```bash
pip install fonttools brotli pillow
npm i @fontsource/anton @fontsource/permanent-marker @fontsource/space-mono \
      @fontsource/space-grotesk @fontsource/instrument-serif
# convert the .woff2 files you need to .ttf (or point --fonts at any folder of the same TTFs)
python3 tools/build_assets.py --fonts <ttf-folder> --out assets
```

`assets/hero-poster.jpg` is the repaired poster that `hero.svg` is built from. Keep it there.

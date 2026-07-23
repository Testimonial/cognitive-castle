# Releasing Cognitive Castle

One-liner: bump the four version files, tag on `develop`, push tag,
create a GitHub Release, and let the `Publish to PyPI` workflow do the
rest.

## Prerequisites (one-time, per project on PyPI)

Trusted Publishing has to be configured at PyPI before the first
release will upload. Without it, `publish.yml` will run and fail at the
final upload step.

1. Register the project name on PyPI (create an empty placeholder, or
   let the first Trusted-Publishing run create it).
2. Go to
   [pypi.org → your project → Publishing](https://pypi.org/manage/project/cognitive-castle/settings/publishing/)
   and add a **new Trusted Publisher** with these values:
   - Owner: `Testimonial`
   - Repository: `cognitive-castle`
   - Workflow filename: `publish.yml`
   - Environment: `pypi`
3. In this repo → Settings → Environments → create an environment
   named **`pypi`** (no secrets needed; the OIDC token is the
   credential).

Once that's done, every future release publishes hands-free.

## Cutting a release

```bash
# From a clean develop
git checkout develop && git pull

# 1. Bump the 4 version sources
NEW=3.5.0
sed -i "s/^__version__ = \".*\"/__version__ = \"${NEW}\"/" cognitive_castle/version.py
sed -i "0,/^version = \".*\"/s//version = \"${NEW}\"/" pyproject.toml
sed -i 's/"version": "[^"]*"/"version": "'"${NEW}"'"/' .claude-plugin/marketplace.json
sed -i 's/"version": "[^"]*"/"version": "'"${NEW}"'"/' .claude-plugin/plugin.json
sed -i 's/"version": "[^"]*"/"version": "'"${NEW}"'"/' .codex-plugin/plugin.json

# 2. Update CHANGELOG.md with the new [<NEW>] section

# 3. Commit + PR + merge (release PR is the standard develop merge flow)
git checkout -b release/v${NEW}
git commit -am "release: v${NEW}"
gh pr create --base develop --title "release: v${NEW}"
gh pr merge --merge --delete-branch

# 4. Tag on develop
git checkout develop && git pull
git tag -a v${NEW} -m "v${NEW}"
git push origin v${NEW}

# 5. Create the GitHub Release
gh release create v${NEW} \
  --title "v${NEW} — headline" \
  --target develop \
  --generate-notes
```

Step 5 triggers `publish.yml`. Monitor with:

```bash
gh run watch
```

## What the publish workflow does

1. Checks out the tag
2. Verifies `cognitive_castle/version.py` matches the tag
3. Builds an sdist + wheel with `python -m build`
4. Runs `twine check dist/*` for metadata sanity
5. Uploads with `pypa/gh-action-pypi-publish` using OIDC — no API
   token stored in the repo

## Manual retry

If the publish job fails after fixing something (e.g. a Trusted
Publisher configuration mistake), retry without cutting a new release:

```bash
gh workflow run publish.yml --field tag=v3.4.0
```

The workflow re-runs against that tag's checkout.

## Rollback

PyPI does not allow re-uploading the same version. If a bad release
lands, yank it on PyPI and cut a `.postN` release:

```bash
NEW=3.5.0.post1  # postN releases are for packaging fixes only
```

Yank the bad version on PyPI (project settings → yank release) so `pip
install cognitive-castle` skips it while leaving reproducibility for
users who pinned it.

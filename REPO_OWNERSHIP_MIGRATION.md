# Rebrand and Repository Ownership Checklist

Use this checklist to move this project to your own repository and brand without breaking existing user installs.

## Keep compatibility first

- Keep `domain: hydros` in `custom_components/hydros/manifest.json`.
- Keep folder path `custom_components/hydros/`.

Changing domain or folder path breaks upgrades for existing users.

## 1) Create your new GitHub repository

Example:

- `github.com/<your-user-or-org>/<your-repo-name>`

## 2) Point local git to your new origin

```bash
git remote rename origin upstream
git remote add origin git@github.com:<your-user-or-org>/<your-repo-name>.git
git push -u origin main
```

## 3) Update integration metadata

Edit these files:

- `custom_components/hydros/manifest.json`
- `hacs.json`
- `README.md`
- `custom_components/hydros/README.md`

Suggested updates:

- `manifest.json`:
  - `name`: your branded integration name
  - `codeowners`: your GitHub handle(s)
  - `documentation`: your repo URL
  - `issue_tracker`: your repo issues URL
- `hacs.json`:
  - `name`: your branded name

## 4) Tag your first independent release

```bash
git tag v0.5.0
git push origin v0.5.0
```

## 5) User migration communication

In release notes, tell users:

- New repository URL
- Install/update instructions in HACS
- That entity IDs remain stable because integration domain is unchanged

## Optional: full technical rebrand (breaking)

Only do this if you are okay with migration work:

- Change folder `custom_components/hydros` to a new domain path
- Change `domain` in `manifest.json`
- Implement migration logic for config entries and entity unique IDs

This is significantly more complex and should be treated as a major release.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const rootPackage = JSON.parse(
  readFileSync(new URL('../package.json', import.meta.url), 'utf8'),
)

const wrappedScriptNames = [
  'dev:mobile:h5',
  'dev:mobile:mp',
  'dev:admin',
  'build:admin',
  'build:mobile:h5',
]

// enforce root npm arg forwarding; workspace wrapper scripts only; verify with node --test tests/root-package-scripts.test.mjs
for (const name of wrappedScriptNames) {
  test(`${name} forwards extra CLI arguments to the nested workspace script`, () => {
    assert.match(
      rootPackage.scripts[name],
      /\s--$/,
      `Expected "${name}" to end with " --" so npm forwards additional args`,
    )
  })
}

// ESLint settings: the code-style and React rules checked by `npm run lint`.
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

// ESLint settings: the rules `npm run lint` checks every .js and .jsx file against.
export default defineConfig([
  // dist is the built output, not code anyone wrote
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    // ready-made rule sets: general JavaScript, the rules of React hooks, and Vite's hot reload
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      // names the browser provides (window, document, fetch), so they are not reported as undefined
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // an unused variable is an error, unless its name starts with a capital letter or an
      // underscore (the pattern is a regular expression matched against the name)
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
    },
  },
])

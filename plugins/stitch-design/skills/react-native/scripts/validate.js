import { validateFile } from '../../../runtime/dist/validate-react.mjs';

if (process.argv.includes('--help')) {
  console.log('Usage: node validate.js <path-to-native-component>');
  process.exit(0);
}

try {
  process.exitCode = validateFile(process.argv[2], { native: true }) ? 0 : 1;
} catch (error) {
  console.error('ERROR:', error.message);
  process.exitCode = 1;
}

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const projectRoot = path.resolve(import.meta.dirname, '..');

function loadMessages(relativePath, exportName) {
  const filePath = path.join(projectRoot, relativePath);
  const source = fs.readFileSync(filePath, 'utf8');
  const expression = source
    .replace(new RegExp(`export\\s+const\\s+${exportName}\\s*=`), 'messages =')
    .replace(/;\s*$/, '');
  const context = { messages: undefined };
  vm.runInNewContext(`${expression}; messages;`, context, {
    filename: filePath,
    timeout: 1000
  });
  if (!context.messages || typeof context.messages !== 'object') {
    throw new Error(`Could not load ${exportName} messages from ${relativePath}`);
  }
  return context.messages;
}

function collectKeys(value, prefix = '') {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return prefix ? [prefix] : [];
  }
  return Object.entries(value).flatMap(([key, child]) => {
    const nextPrefix = prefix ? `${prefix}.${key}` : key;
    return collectKeys(child, nextPrefix);
  });
}

function diffKeys(left, right) {
  const rightSet = new Set(right);
  return left.filter((key) => !rightSet.has(key));
}

const en = loadMessages('src/i18n/en.ts', 'en');
const zh = loadMessages('src/i18n/zh.ts', 'zh');
const enKeys = collectKeys(en).sort();
const zhKeys = collectKeys(zh).sort();
const missingInZh = diffKeys(enKeys, zhKeys);
const missingInEn = diffKeys(zhKeys, enKeys);

const requiredNamespaces = [
  'dashboard',
  'settings',
  'newAnalysis',
  'runMonitor',
  'results',
  'databases',
  'agent'
];
const missingNamespaces = requiredNamespaces.filter((key) => !(key in en) || !(key in zh));

if (missingInZh.length || missingInEn.length || missingNamespaces.length) {
  console.error('i18n smoke check failed.');
  if (missingInZh.length) {
    console.error(`Missing in zh: ${missingInZh.join(', ')}`);
  }
  if (missingInEn.length) {
    console.error(`Missing in en: ${missingInEn.join(', ')}`);
  }
  if (missingNamespaces.length) {
    console.error(`Missing required namespace(s): ${missingNamespaces.join(', ')}`);
  }
  process.exit(1);
}

console.log(`i18n smoke check passed (${enKeys.length} keys).`);

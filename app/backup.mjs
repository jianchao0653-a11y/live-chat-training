import { DatabaseSync, backup } from 'node:sqlite';
import { existsSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const project=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const source=resolve(project,'runtime/lens.sqlite');
if(!existsSync(source)) throw new Error('尚无本地数据库，无需备份。');
const directory=resolve(project,'runtime/backups');
mkdirSync(directory,{recursive:true});
const destination=resolve(directory,`lens-${new Date().toISOString().replace(/[:.]/g,'-')}-${randomUUID().slice(0,8)}.sqlite`);
if(existsSync(destination)) throw new Error('备份目标已存在，拒绝覆盖。');
const database=new DatabaseSync(source,{readOnly:true});
try { await backup(database,destination); console.log(`SQLite 一致性备份已创建：${destination}`); }
finally { database.close(); }

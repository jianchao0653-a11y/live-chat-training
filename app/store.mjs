import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';

export const now = () => new Date().toISOString();
export const hash = (value) => createHash('sha256').update(value).digest('hex');
export const customerSegments = ['UNCLASSIFIED', 'NEW', 'MAINTAIN'];

export function openStore(file, {legacySchema=false,legacyVersion}={}) {
  if(legacyVersion!==undefined && ![1,2].includes(legacyVersion))throw new Error('Unsupported legacy schema version');
  if(legacySchema && legacyVersion!==undefined && legacyVersion!==1)throw new Error('Conflicting legacy schema versions');
  const targetVersion=legacySchema?1:legacyVersion??3;
  if(targetVersion<3 && file!==':memory:')throw new Error('Legacy schema construction is memory-only');
  if (file !== ':memory:') mkdirSync(dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec(`PRAGMA foreign_keys=ON; PRAGMA secure_delete=ON;
    CREATE TABLE IF NOT EXISTS people (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, platform TEXT NOT NULL, stage TEXT NOT NULL,
      notes TEXT NOT NULL DEFAULT '', boundary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS analyses (
      id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
      input TEXT NOT NULL, goal TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL,
      mode TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(person_id, fingerprint)
    );
    CREATE TABLE IF NOT EXISTS claims (
      id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS outcomes (
      analysis_id TEXT PRIMARY KEY REFERENCES analyses(id) ON DELETE CASCADE,
      status TEXT NOT NULL, note TEXT NOT NULL, draft TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS beliefs (
      analysis_id TEXT PRIMARY KEY REFERENCES analyses(id) ON DELETE CASCADE,
      proposition TEXT NOT NULL, prior REAL NOT NULL, likelihood REAL NOT NULL,
      posterior REAL NOT NULL, evidence TEXT NOT NULL, alternative TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'UNCONFIRMED', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, scope TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
  `);
  const all = (sql, ...args) => db.prepare(sql).all(...args);
  const get = (sql, ...args) => db.prepare(sql).get(...args);
  const run = (sql, ...args) => db.prepare(sql).run(...args);
  let transactionDepth=0;
  const tx = fn => {
    const nested=transactionDepth>0,savepoint=`lens_${transactionDepth}`;
    db.exec(nested?`SAVEPOINT ${savepoint}`:'BEGIN IMMEDIATE');transactionDepth++;
    try{const result=fn();db.exec(nested?`RELEASE ${savepoint}`:'COMMIT');return result;}
    catch(e){db.exec(nested?`ROLLBACK TO ${savepoint}; RELEASE ${savepoint}`:'ROLLBACK');throw e;}
    finally{transactionDepth--;}
  };
  // Transactional, additive migration: never reinterpret legacy relationships as shared facts.
  if (get('PRAGMA user_version').user_version < 1) tx(() => {
    db.exec(`CREATE TABLE streamers (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, tone TEXT NOT NULL DEFAULT '',
      phrases TEXT NOT NULL DEFAULT '', emojis TEXT NOT NULL DEFAULT '',
      boundary TEXT NOT NULL DEFAULT '', input_layout TEXT NOT NULL DEFAULT 'SYSTEM', revision INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE pairs (
      id TEXT PRIMARY KEY, streamer_id TEXT NOT NULL REFERENCES streamers(id),
      person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
      stage TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', boundary TEXT NOT NULL DEFAULT '',
      revision INTEGER NOT NULL DEFAULT 0, UNIQUE(streamer_id, person_id)
    );
    ALTER TABLE analyses ADD COLUMN pair_id TEXT REFERENCES pairs(id) ON DELETE CASCADE;
    ALTER TABLE claims ADD COLUMN pair_id TEXT REFERENCES pairs(id) ON DELETE CASCADE;
    CREATE TABLE context_events (
      seq INTEGER PRIMARY KEY AUTOINCREMENT, pair_id TEXT NOT NULL REFERENCES pairs(id) ON DELETE CASCADE,
      type TEXT NOT NULL, subject_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE INDEX analyses_pair ON analyses(pair_id, created_at);
    CREATE INDEX claims_pair ON claims(pair_id, created_at);`);
    for (let n = 1; n <= 6; n++) {
      const id = String(n).padStart(4, '0');
      run('INSERT INTO streamers(id,name) VALUES(?,?)', id, `待设置主播 ${id}`);
    }
    for (const p of all('SELECT * FROM people')) {
      const pairId = randomUUID();
      run('INSERT INTO pairs(id,streamer_id,person_id,stage,notes,boundary) VALUES(?,?,?,?,?,?)', pairId, '0001', p.id, p.stage, p.notes, p.boundary);
      run('UPDATE analyses SET pair_id=? WHERE person_id=?', pairId, p.id);
      run('UPDATE claims SET pair_id=? WHERE person_id=?', pairId, p.id);
    }
    const max = get('SELECT MAX(CAST(id AS INTEGER)) AS n FROM people').n || 0;
    const seq = Number(get("SELECT value FROM settings WHERE key='person_sequence'")?.value || 0);
    run("INSERT INTO settings VALUES('person_sequence',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", String(Math.max(max, seq)));
    db.exec('PRAGMA user_version=1');
  });
  const pair = (personId, streamerId = '0001') => get('SELECT * FROM pairs WHERE person_id=? AND streamer_id=?', personId, streamerId);
  if (targetVersion>=2 && get('PRAGMA user_version').user_version < 2) tx(() => {
    db.exec(`ALTER TABLE streamers ADD COLUMN goal TEXT NOT NULL DEFAULT '';
      ALTER TABLE streamers ADD COLUMN tags TEXT NOT NULL DEFAULT '';
      ALTER TABLE claims ADD COLUMN review_state TEXT NOT NULL DEFAULT 'CONFIRMED';
      ALTER TABLE claims ADD COLUMN category TEXT NOT NULL DEFAULT 'MEMORY';
      UPDATE claims SET review_state='PENDING' WHERE kind='INFERRED';
      PRAGMA user_version=2;`);
  });
  if (targetVersion>=3 && get('PRAGMA user_version').user_version < 3) tx(() => {
    db.exec(`ALTER TABLE pairs ADD COLUMN segment TEXT NOT NULL DEFAULT 'UNCLASSIFIED' CHECK(segment IN ('UNCLASSIFIED','NEW','MAINTAIN'));
      PRAGMA user_version=3;`);
  });
  const hasSegment=get('PRAGMA user_version').user_version>=3;
  const event = (pairId, type, subjectId, payload) => {
    run('INSERT INTO context_events(pair_id,type,subject_id,payload,created_at) VALUES(?,?,?,?,?)', pairId, type, subjectId, JSON.stringify(payload), now());
    run('UPDATE pairs SET revision=revision+1 WHERE id=?', pairId);
  };
  const person = (id, streamerId = '0001') => {
    const p = get('SELECT id,name,platform,created_at FROM people WHERE id=?', id);
    if (!p) return null;
    const relation = pair(id, streamerId);
    return { ...p, segment: relation?.segment || 'UNCLASSIFIED', stage: relation?.stage || '初识', notes: relation?.notes || '', boundary: relation?.boundary || '',
      relationship: relation || null, streamer: get('SELECT * FROM streamers WHERE id=?', streamerId),
      claims: relation ? all(`SELECT c.* FROM claims c WHERE pair_id=? ORDER BY
        COALESCE((SELECT MAX(seq) FROM context_events e WHERE e.subject_id=c.id),0) DESC,created_at DESC,id`, relation.id) : [] };
  };
  const analysis = (id) => {
    const row = get('SELECT a.*, p.name, p.platform, r.streamer_id FROM analyses a JOIN people p ON p.id=a.person_id JOIN pairs r ON r.id=a.pair_id WHERE a.id=?', id);
    return row ? { ...row, result: JSON.parse(row.result), outcome: get('SELECT * FROM outcomes WHERE analysis_id=?', id) || null,
      belief: get('SELECT * FROM beliefs WHERE analysis_id=?', id) || null } : null;
  };
  return {
    db, get, run, all, tx, analysis, pair, person,
    isBeliefBlocked: (pairId, proposition) => Boolean(get(`SELECT 1 FROM beliefs b JOIN analyses a ON a.id=b.analysis_id
      WHERE a.pair_id=? AND b.proposition=? AND b.status IN ('DISPUTED','RETIRED') LIMIT 1`,pairId,proposition)),
    streamers: () => all('SELECT * FROM streamers ORDER BY id'),
    people: (streamerId = '0001') => all(`SELECT p.id,p.name,p.platform,p.created_at,r.id AS pair_id,COALESCE(r.stage,'未建立') AS stage,COALESCE(r.notes,'') AS notes,
      ${hasSegment?"COALESCE(r.segment,'UNCLASSIFIED')":"'UNCLASSIFIED'"} AS segment,
      (SELECT COUNT(*) FROM analyses WHERE pair_id=r.id) as analysis_count FROM people p
      LEFT JOIN pairs r ON r.person_id=p.id AND r.streamer_id=? ORDER BY p.id`, streamerId),
    updateStreamer: (id, s) => run('UPDATE streamers SET name=?,tone=?,phrases=?,emojis=?,boundary=?,input_layout=?,goal=?,tags=?,revision=revision+1 WHERE id=?', s.name, s.tone, s.phrases, s.emojis, s.boundary, s.input_layout, s.goal||'', s.tags||'', id),
    updatePerson: (id, streamerId, p) => tx(() => {
      run('UPDATE people SET name=?,platform=? WHERE id=?', p.name, p.platform, id);
      // Keep old columns as a migration-only snapshot, not a second live source of truth.
      run(`INSERT INTO pairs(id,streamer_id,person_id,stage,notes,boundary) VALUES(?,?,?,?,?,?)
        ON CONFLICT(streamer_id,person_id) DO UPDATE SET stage=excluded.stage,notes=excluded.notes,boundary=excluded.boundary`,
        randomUUID(), streamerId, id, p.stage, p.notes, p.boundary);
      event(pair(id, streamerId).id, 'RELATIONSHIP_UPDATED', id, {});
    }),
    setCustomerSegment: (id, streamerId, segment) => tx(() => {
      if(!hasSegment || !customerSegments.includes(segment))throw new Error('Invalid customer segment');
      const relation=pair(id,streamerId);
      if(!relation)throw new Error('Customer relationship does not exist');
      if(relation.segment===segment)return {changed:false,person:person(id,streamerId)};
      run('UPDATE pairs SET segment=?,revision=revision+1 WHERE id=?',segment,relation.id);
      return {changed:true,person:person(id,streamerId)};
    }),
    addClaim: (c) => tx(() => {
      run('INSERT INTO claims(id,person_id,kind,content,source,created_at,pair_id,review_state,category) VALUES(?,?,?,?,?,?,?,?,?)', c.id, c.person_id, c.kind, c.content, c.source, c.created_at, c.pair_id,c.review_state||(c.kind==='INFERRED'?'PENDING':'CONFIRMED'),c.category||'MEMORY');
      event(c.pair_id, 'MEMORY_ADDED', c.id, { kind: c.kind });
    }),
    setClaimStatus: (id, kind) => tx(() => {
      const c = get('SELECT * FROM claims WHERE id=?', id);
      run('UPDATE claims SET kind=? WHERE id=?', kind, id);
      event(c.pair_id, 'MEMORY_STATUS', id, { previous: c.kind, kind });
    }),
    deleteClaim: (id) => tx(() => {
      const c = get('SELECT * FROM claims WHERE id=?', id);
      if (!c) return;
      run('DELETE FROM claims WHERE id=?', id);
      event(c.pair_id, 'MEMORY_DELETED', id, {});
    }),
    saveOutcome: (id, o) => tx(() => {
      const a = analysis(id);
      if(a.outcome && ['status','note','draft'].every(k=>a.outcome[k]===o[k]))return;
      run(`INSERT INTO outcomes VALUES(?,?,?,?,?) ON CONFLICT(analysis_id) DO UPDATE SET status=excluded.status,note=excluded.note,draft=excluded.draft,created_at=excluded.created_at`, id, o.status, o.note, o.draft, now());
      event(a.pair_id, 'OUTCOME_RECORDED', id, {status:o.status});
    }),
    setBeliefStatus: (id, status) => tx(() => {
      const a = analysis(id);
      run('UPDATE beliefs SET status=? WHERE analysis_id=?', status, id);
      event(a.pair_id, 'BELIEF_STATUS', id, { previous: a.belief.status, status });
    }),
    context: (id, streamerId = '0001') => {
      const p = person(id, streamerId);
      if (!p?.relationship) return null;
      const pairId = p.relationship.id;
      const history = all(`SELECT a.id,a.input,a.goal,a.result,a.created_at,o.status,o.note,o.draft,o.created_at AS observed_at
        FROM analyses a JOIN outcomes o ON o.analysis_id=a.id WHERE a.pair_id=? ORDER BY
        COALESCE((SELECT MAX(seq) FROM context_events e WHERE e.subject_id=a.id AND e.type='OUTCOME_RECORDED'),0) DESC,o.created_at DESC,a.rowid DESC LIMIT 200`, pairId);
      // Corrections replace an observation; reruns of identical evidence are not independent samples.
      const seen = new Set();
      const outcomes = history.filter(a => {
        a.result = JSON.parse(a.result);
        const key = hash(JSON.stringify([a.input,a.goal,a.result.strategy]));
        if (seen.has(key)) return false; seen.add(key); return true;
      }).map(a => ({ analysis_id:a.id, goal:a.goal, situation:a.result.situation || 'LEGACY_UNKNOWN', strategy:a.result.strategy,
        status:a.status, note:a.note.slice(0,1000), draft:a.draft.slice(0,1000), observed_at:a.observed_at }));
      const beliefRows = all(`SELECT b.* FROM beliefs b JOIN analyses a ON a.id=b.analysis_id WHERE a.pair_id=?
        AND b.status IN ('SUPPORTED','DISPUTED','RETIRED') ORDER BY
        COALESCE((SELECT MAX(seq) FROM context_events e WHERE e.subject_id=b.analysis_id AND e.type='BELIEF_STATUS'),0) DESC,b.created_at DESC,a.rowid DESC LIMIT 12`, pairId);
      return { ...p, claims:p.claims.filter(c => c.review_state==='CONFIRMED' && ['FACT','SELF_DECLARED','INFERRED'].includes(c.kind)).slice(0,8),
        excluded_memories:p.claims.filter(c => ['DISPUTED','EXPIRED'].includes(c.kind)).slice(0,8),
        beliefs:beliefRows, outcomes:outcomes.slice(0,5),
        strategy_observations:outcomes.map(({analysis_id,goal,situation,strategy,status}) => ({analysis_id,goal,situation,strategy,status})),
        retrieval_policy:'pair-only / latest 8 active memories, 8 corrections, 12 reviewed hypotheses, 5 outcomes / at most 200 outcome records for statistics' };
    },
    createPerson: (p, assignedId) => tx(() => {
      // MAX preserves monotonically increasing IDs using a separate sequence even after deletion.
      const previous = Number(get("SELECT value FROM settings WHERE key='person_sequence'")?.value || 0);
      const id = assignedId || String(previous + 1).padStart(4, '0');
      run("INSERT INTO settings VALUES('person_sequence',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", String(previous + 1));
      run('INSERT INTO people VALUES(?,?,?,?,?,?,?)', id, p.name, p.platform, p.stage, p.notes || '', p.boundary || '', now());
      run('INSERT INTO pairs(id,streamer_id,person_id,stage,notes,boundary) VALUES(?,?,?,?,?,?)', randomUUID(), p.streamer_id || '0001', id, p.stage, p.notes || '', p.boundary || '');
      if(hasSegment && p.segment!==undefined){
        if(!customerSegments.includes(p.segment))throw new Error('Invalid customer segment');
        run('UPDATE pairs SET segment=? WHERE person_id=? AND streamer_id=?',p.segment,id,p.streamer_id||'0001');
      }
      return id;
    }),
    saveAnalysis: (p, text, goal, fingerprint, result, mode, belief) => tx(() => {
      const existing = get('SELECT id FROM analyses WHERE person_id=? AND fingerprint=?', p.id, fingerprint);
      if (existing) return analysis(existing.id);
      const id = randomUUID();
      run('INSERT INTO analyses(id,person_id,input,goal,fingerprint,result,mode,created_at,pair_id) VALUES(?,?,?,?,?,?,?,?,?)', id, p.id, text, goal, fingerprint, JSON.stringify(result), mode, now(), p.relationship?.id || pair(p.id).id);
      if (belief) run('INSERT INTO beliefs VALUES(?,?,?,?,?,?,?,?,?)', id, belief.proposition, belief.prior, belief.likelihood, belief.posterior, belief.evidence, belief.alternative, 'UNCONFIRMED', now());
      return analysis(id);
    }),
    deletePerson: (id) => tx(() => {
      run('DELETE FROM people WHERE id=?', id);
      const receipt = { id: randomUUID(), scope: '人物及关联分析、证据、信念、反馈', created_at: now() };
      run('INSERT INTO receipts VALUES(?,?,?)', receipt.id, receipt.scope, receipt.created_at);
      return receipt;
    }),
    close: () => db.close(),
  };
}

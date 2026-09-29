# Module 2b · Vector ใน Neo4j

**11:05 – 11:30** (25 นาที) · ต่อจาก [Module 2a: Vector ใน PostgreSQL](02-module2a-pg-vec.md)

---

## เป้าหมาย

ทำสิ่งเดียวกับ Module 2a ก่อนหน้าอีกครั้ง แต่คราวนี้ใน Neo4j ซึ่งเก็บ vector เป็น **property ของ node โดยตรง** ไม่ใช่คอลัมน์แยกแบบ PostgreSQL

ระบบในขณะนี้ **มี embedding พร้อมใช้งานอยู่แล้ว** เช่นกัน ขั้นตอนแรกของ lab นี้คือการลบข้อมูลดังกล่าวออก เพื่อให้ผู้เรียนได้สร้างขึ้นใหม่ด้วยตนเอง

---

## ขั้นที่ 0 · ตรวจสอบข้อมูลเดิมก่อนลบ

เปิด Neo4j Browser ([http://localhost:7474](http://localhost:7474)) รัน:

```cypher
MATCH (n) WHERE n.embedding IS NOT NULL RETURN labels(n)[0] AS label, count(n) AS n;
```

ควรเห็น `Device` และ `Circuit` มี embedding อยู่แล้วทั้งคู่

---

## ขั้นที่ 1 · ลบทิ้ง

**Neo4j Browser** — รัน:
```cypher
DROP INDEX device_embedding IF EXISTS;
DROP INDEX circuit_embedding IF EXISTS;

MATCH (d:Device)  REMOVE d.embedding;
MATCH (c:Circuit) REMOVE c.embedding;

// ยืนยันผล ควรได้ 0
MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS nodes_with_embedding;
```

หมายเหตุ: `make lab1-reset` ลบ vector ทั้งใน PostgreSQL และ Neo4j พร้อมกันในคำสั่งเดียว หากทำ [Module 2a: Vector ใน PostgreSQL](02-module2a-pg-vec.md) ด้วย `make lab1-reset` มาแล้ว Neo4j ถูกลบไปพร้อมกันแล้วเช่นกัน — ขั้นตอนนี้สำหรับกรณีที่ลบเฉพาะฝั่ง PostgreSQL ด้วย SQL ตรงๆ มาก่อน

ลองค้นหา Device ที่คล้ายกันผ่าน MCP Inspector อีกครั้ง — ระบบจะตอบว่ายังไม่มี vector index

---

## ขั้นที่ 2 · สร้าง vector index

ต้องสร้าง index สองตัวแยกกัน เพราะมีสอง label ที่ต้องการ semantic search (`Device` และ `Circuit`) — สร้างก่อนได้เลยแม้ node ยังไม่มี property `embedding` เลยก็ตาม (ต่างจาก HNSW ของ pgvector ที่ต้องรอ backfill ก่อนจึงค่อยสร้าง):

```cypher
CREATE VECTOR INDEX device_embedding IF NOT EXISTS
FOR (d:Device) ON (d.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX circuit_embedding IF NOT EXISTS
FOR (c:Circuit) ON (c.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};
```

ตรวจสอบว่า index ถูกสร้างจริง (ควรเห็น 2 แถว สถานะ `ONLINE`):

```cypher
SHOW VECTOR INDEXES YIELD name, state WHERE name IN ['device_embedding', 'circuit_embedding'];
```

---

## ขั้นที่ 3 · Backfill ด้วยสคริปต์อ้างอิง

ข้อความที่ต้อง embed ไม่ใช่ทั้ง node แต่เป็นฟิลด์ `profile_text` ที่ seed ไว้ให้แล้ว — ตัวอย่างจริง: `"CR-BKK-01 is a core router carrying backbone transit between sites. Located at site BKK. Management address 10.10.0.1. Interfaces: Hu0/0/0/0, Hu0/0/0/1, Hu0/0/0/2."`

แทนที่จะเขียนเองเหมือน `my_embed.py` ใน Module 2a รอบนี้ใช้สคริปต์อ้างอิงที่มีอยู่แล้วได้เลย (โค้ดตัวอย่างอยู่ใน [`docker/seeder/seed_neo4j.py`](../../docker/seeder/seed_neo4j.py) — วนทั้ง `Device` และ `Circuit` ในลูปเดียว เพราะ logic เหมือนกันทุกประการ ต่างแค่ label):

```bash
uv run python scripts/embed_devices.py
```

**ผลลัพธ์ที่ควรเห็น** (รันจริงตอนเตรียมเอกสารนี้):

```
embedded 10 Device nodes
embedded 35 Circuit nodes

45 nodes now carry embeddings
```

ยืนยันด้วยคำสั่งเดียวกับขั้นที่ 0:

```cypher
MATCH (n) WHERE n.embedding IS NOT NULL RETURN labels(n)[0] AS label, count(n) AS n;
```

ควรได้ `Device = 10` และ `Circuit = 35`

---

## ขั้นที่ 4 · ทดสอบค้นหา

```cypher
MATCH (d:Device {device_id: "CR-BKK-01"})
CALL db.index.vector.queryNodes('device_embedding', 3, d.embedding)
YIELD node, score
RETURN node.device_id AS id, score
```

**ผลลัพธ์ที่ควรเห็น** — ค้นหาอุปกรณ์ที่ใกล้เคียงกับ `CR-BKK-01` เอง:

```
{'id': 'CR-BKK-01', 'score': 0.9996}
{'id': 'CR-BKK-02', 'score': 0.9792}
{'id': 'PE-BKK-02', 'score': 0.8869}
```

อุปกรณ์ตัวเองได้คะแนนสูงสุดเสมอ (ใกล้ 1.0) ตามด้วย `CR-BKK-02` ซึ่งเป็น core router เหมือนกัน — เป็นหลักฐานว่า embedding จับ "บทบาทของอุปกรณ์" ได้ ไม่ใช่แค่จับชื่อที่คล้ายกัน

ลองถามคำถามเดิมจากขั้นที่ 0 ของ [Module 2a: Vector ใน PostgreSQL](02-module2a-pg-vec.md) ผ่าน Chainlit อีกครั้ง — ตอนนี้ระบบควรตอบ semantic search ได้ครบทั้งสองฐานข้อมูลแล้ว

---

## เครื่องมือเสริม: ลองคำค้นอื่น ๆ แบบเร็วด้วย `scripts/vec_query.py`

ถ้าอยากลองคำค้นอื่นแบบเร็ว ๆ โดยไม่ต้องเปิด Neo4j Browser แล้วพิมพ์ Cypher เอง มีเครื่องมือสำเร็จรูปให้: [`scripts/vec_query.py`](../../scripts/vec_query.py) แปลงคำค้นเป็น embedding แล้วพิมพ์ Cypher เต็มรูปแบบ (มี vector จริงฝังอยู่) ออกมาให้ก็อปวางใน Neo4j Browser ได้ทันที — ตัวสคริปต์เองไม่เชื่อมต่อฐานข้อมูลเลย เลือกฝั่ง `device` หรือ `circuit` ด้วย `--label`:

```bash
uv run python scripts/vec_query.py neo4j "อุปกรณ์ core router ที่เชื่อมต่อ backbone ระหว่างไซต์"
```

```bash
uv run python scripts/vec_query.py neo4j "วงจร MPLS-VPN ความเร็ว 50 Mbps" --label circuit
```

**ตัวอย่างผลลัพธ์จริงของคำสั่งแรก** (ตัดมาแสดงบางส่วน — vector เต็ม 1024 มิติ ยาวประมาณ 50 บรรทัด รันจริงแล้วจะได้ statement เต็มพร้อมวาง):

```cypher
CALL db.index.vector.queryNodes('device_embedding', 5, [0.0038,-0.0276,-0.0413,0.0085,-0.001,-0.0001,0.0456,0.0086,-0.0002,-0.0064,-0.0049,0.0334,-0.0058,0.0005,0.0387,-0.0122,0.0255,-0.0181,0.0405,-0.0271,
-0.0152,-0.0389,-0.0152,0.0138,0.0287,0.0172,0.0281,0.0128,0.007,0.0433,-0.0138,-0.0385,0.0722,-0.0052,-0.0583,-0.0442,0.0071,-0.0181,-0.0624,-0.0129,
... (ตัดออก ~48 บรรทัด) ...
])
YIELD node, score
RETURN node.device_id AS id, score;
```

ก็อป statement **เต็ม** ที่ได้จากการรันจริง (ไม่ใช่ตัวอย่างที่ตัดมาด้านบน) ไปวางใน Neo4j Browser ได้เลย — คำค้นด้าน `circuit` จะได้ Cypher รูปแบบเดียวกัน แต่ index เป็น `circuit_embedding` และคืนค่า `circuit_id` แทน

---

## เกณฑ์ผ่าน

- [ ] `device_embedding` และ `circuit_embedding` ถูกสร้างครบทั้งสอง index สถานะ `ONLINE`
- [ ] `MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n)` ได้ 45 (10 Device + 35 Circuit)
- [ ] `db.index.vector.queryNodes` คืนผลลัพธ์ที่สมเหตุสมผล (อุปกรณ์ประเภทเดียวกันควรมีคะแนนใกล้กัน)
- [ ] Chainlit ตอบคำถาม semantic ได้อีกครั้งทั้งสองฐานข้อมูล

---

## โบนัส

**เดินกราฟต่อจากผลค้นหา** — จากผลของขั้นที่ 4 เขียน Cypher ต่ออีกหนึ่ง `MATCH` เพื่อหาว่า `CR-BKK-02` เชื่อมกับ `Circuit` ใดบ้าง ในคำสั่งเดียวกับที่ query vector — นี่คือสิ่งที่ pgvector ทำไม่ได้: ผลจาก semantic search ใน Neo4j เดินกราฟต่อได้ทันทีโดยไม่ต้องเอาผลลัพธ์ไปสืบต่อในระบบอื่น

<details>
<summary>หากใช้เวลาเกิน 10 นาทีแล้วยังไม่สำเร็จ คลิกเพื่อดูเฉลย</summary>

- โค้ด backfill อ้างอิงเต็มรูปแบบอยู่ที่ `scripts/embed_devices.py` (`make embed-devices`)
- ถ้า endpoint ต่อไม่ได้ ให้ใช้ `LLM_MODEL_FAST` และตรวจ VPN

</details>

---

## สิ่งที่ต้องส่ง

ผลลัพธ์การค้นหาจริงจากขั้นที่ 4 (คัดลอกจาก Neo4j Browser)

---

## ต่อไป

→ [Module 2c: Embeddings กับ OpenSearch](04-module2c-opensearch-vec.md) — ฐานข้อมูลตัวที่ 3 ที่เก็บ vector ได้ และเป็นตัวที่ production เลือกใช้เป็นหลัก

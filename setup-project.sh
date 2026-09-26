#!/bin/bash
# Mendokumentasikan (dan dapat membangun ulang) konfigurasi GitHub Project V2
# "HERO — Papan Proyek" milik org hero-ojk-its: https://github.com/orgs/hero-ojk-its/projects/1
#
# Struktur papan — acuan: docs/07-wbs-sprint-plan.md, docs/06-product-backlog-user-stories.md
#   Status      : Backlog · To Do · In Progress · In Review / Testing · Menunggu Mitra · Done
#   Sprint      : iteration Inception (31 Agu–15 Sep) + Sprint 1–7, 2 minggu Rabu–Selasa;
#                 Sprint Review di rapat mingguan Selasa terakhir tiap sprint
#   Peran       : PM/BA · Backend · Frontend · Data/ML · Infra/QA   (Data/ML belum bisa di-assign)
#   Prioritas   : Must · Should · Could   (sama dengan label prio:)
#   Story Point : angka, dari tabel "Rincian" di badan issue
#   Blocker / Remarks : teks bebas — kendala disampaikan di awal (MoM #2)
#   Fase        : memakai field bawaan Milestone
#
# Isi kartu (status, sprint, catatan) dikelola langsung di papan, bukan di skrip ini.
#
# Prasyarat: gh auth refresh -h github.com -s project,read:project
# Catatan  : skrip ini hanya membuat papan bila belum ada. Workflow bawaan papan
#            (Item closed → Done, dst.) tidak dapat diaktifkan lewat API — atur di
#            Settings → Workflows pada papan.
set -euo pipefail

OWNER="hero-ojk-its"
REPO="hero-ojk-its/hero"
TITLE="HERO — Papan Proyek"

existing=$(gh project list --owner "$OWNER" --format json --jq ".projects[] | select(.title==\"$TITLE\") | .number" 2>/dev/null || true)
if [ -n "$existing" ]; then
  echo "Project '$TITLE' sudah ada (#$existing). Tidak dibuat ulang."
  exit 0
fi

NUM=$(gh project create --owner "$OWNER" --title "$TITLE" --format json --jq '.number')
PID=$(gh project view "$NUM" --owner "$OWNER" --format json --jq '.id')
gh project link "$NUM" --owner "$OWNER" --repo "$REPO" >/dev/null
gh project edit "$NUM" --owner "$OWNER" \
  --description "Kanban sprint HERO · Capstone ITS × OJK DPEA · 31 Agu – 24 Des 2026" >/dev/null
echo "✓ Project #$NUM dibuat dan ditautkan ke $REPO"

# ---------- Status ----------
STATUS_FID=$(gh project field-list "$NUM" --owner "$OWNER" --format json --jq '.fields[] | select(.name=="Status") | .id')
gh api graphql -f query='
mutation($f:ID!){ updateProjectV2Field(input:{fieldId:$f, singleSelectOptions:[
  {name:"Backlog",             color:GRAY,   description:"Terjadwal di fase/sprint mendatang"},
  {name:"To Do",               color:BLUE,   description:"Siap dikerjakan pada sprint berjalan"},
  {name:"In Progress",         color:YELLOW, description:"Sedang dikerjakan"},
  {name:"In Review / Testing", color:PURPLE, description:"PR terbuka, menunggu review atau pengujian"},
  {name:"Menunggu Mitra",      color:ORANGE, description:"Terblokir menunggu data/keputusan DPEA"},
  {name:"Done",                color:GREEN,  description:"Memenuhi Definition of Done"}
]}){ clientMutationId } }' -f f="$STATUS_FID" >/dev/null
echo "✓ Status"

# ---------- Sprint (iteration) ----------
gh api graphql -f query='
mutation($p:ID!){ createProjectV2Field(input:{projectId:$p, dataType:ITERATION, name:"Sprint",
  iterationConfiguration:{startDate:"2026-08-31", duration:14, iterations:[
    {title:"Inception · pra-sprint (Fase 0)", startDate:"2026-08-31", duration:16},
    {title:"Sprint 1 · Scraping & Ingest",    startDate:"2026-09-16", duration:14},
    {title:"Sprint 2 · Scraping & Ingest",    startDate:"2026-09-30", duration:14},
    {title:"Sprint 3 · Analisa & Summary",    startDate:"2026-10-14", duration:14},
    {title:"Sprint 4 · Analisa & Summary",    startDate:"2026-10-28", duration:14},
    {title:"Sprint 5 · Harmonisasi",          startDate:"2026-11-11", duration:14},
    {title:"Sprint 6 · Tanggapan PoV",        startDate:"2026-11-25", duration:14},
    {title:"Sprint 7 · Stabilisasi & UAT",    startDate:"2026-12-09", duration:14}
]}}){ clientMutationId } }' -f p="$PID" >/dev/null
echo "✓ Inception + Sprint 1–7"

# ---------- Field kustom ----------
gh project field-create "$NUM" --owner "$OWNER" --name "Peran" --data-type SINGLE_SELECT \
  --single-select-options "PM/BA,Backend,Frontend,Data/ML,Infra/QA" >/dev/null
gh project field-create "$NUM" --owner "$OWNER" --name "Prioritas" --data-type SINGLE_SELECT \
  --single-select-options "Must,Should,Could" >/dev/null
gh project field-create "$NUM" --owner "$OWNER" --name "Story Point" --data-type NUMBER >/dev/null
gh project field-create "$NUM" --owner "$OWNER" --name "Blocker / Remarks" --data-type TEXT >/dev/null
echo "✓ Peran · Prioritas · Story Point · Blocker / Remarks"

# ---------- Views ----------
fid() { gh api "orgs/$OWNER/projectsV2/$NUM/fields" --jq ".[] | select(.name==\"$1\") | .id"; }
A=$(fid Assignees); ST=$(fid Status); MS=$(fid Milestone); SP=$(fid "Story Point"); SPR=$(fid Sprint)
PER=$(fid Peran); REM=$(fid "Blocker / Remarks"); PRI=$(fid Prioritas); PR=$(fid "Linked pull requests")
view() { gh api -X POST "orgs/$OWNER/projectsV2/$NUM/views" --input - --jq '"  ✓ view " + .name'; }

view <<EOF
{"name":"🏃 Sprint Berjalan","layout":"board","filter":"sprint:@current","visible_fields":[$A,$PER,$PRI,$SP,$REM],"vertical_group_by":[$ST],"sort_by":[[$PRI,"asc"]]}
EOF
view <<EOF
{"name":"🗂 Kanban per Fase","layout":"board","visible_fields":[$A,$SPR,$PER,$PRI,$SP],"vertical_group_by":[$ST],"group_by":[$MS],"sort_by":[[$SPR,"asc"]]}
EOF
view <<EOF
{"name":"⏳ Menunggu Mitra","layout":"table","filter":"status:\"Menunggu Mitra\"","visible_fields":[$PER,$A,$SPR,$MS,$REM],"sort_by":[[$SPR,"asc"]]}
EOF
view <<EOF
{"name":"📋 Backlog per Sprint","layout":"table","visible_fields":[$ST,$PER,$A,$PRI,$SP,$MS,$REM,$PR],"group_by":[$SPR],"sort_by":[[$ST,"asc"]]}
EOF
view <<EOF
{"name":"🗓 Roadmap","layout":"roadmap","visible_fields":[$ST,$A],"group_by":[$MS],"sort_by":[[$SPR,"asc"]]}
EOF
view <<EOF
{"name":"👥 Per Peran","layout":"board","filter":"-status:Done","visible_fields":[$A,$SPR,$PRI,$SP],"vertical_group_by":[$ST],"group_by":[$PER],"sort_by":[[$PRI,"asc"]]}
EOF
view <<EOF
{"name":"👤 Tugas Saya","layout":"table","filter":"assignee:@me -status:Done","visible_fields":[$ST,$SPR,$PRI,$SP,$REM],"sort_by":[[$SPR,"asc"]]}
EOF

echo
echo "Selesai: https://github.com/orgs/$OWNER/projects/$NUM"
echo "Hapus view bawaan yang tidak terpakai, lalu aktifkan workflow di Settings → Workflows."

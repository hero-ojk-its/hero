#!/bin/bash
# Membuat GitHub Project V2 "HERO — Papan Proyek" untuk org hero-ojk-its
# dengan struktur: Milestone (Fase) · Task · Status · PIC · Blocker/Remarks · Sprint
#
# Prasyarat: gh auth refresh -h github.com -s project,read:project,workflow
set -euo pipefail

OWNER="hero-ojk-its"
REPO="hero-ojk-its/hero"
TITLE="HERO — Papan Proyek"

# ---------- 0. Cek apakah sudah ada ----------
existing=$(gh project list --owner "$OWNER" --format json --jq ".projects[] | select(.title==\"$TITLE\") | .number" 2>/dev/null || true)
if [ -n "$existing" ]; then
  echo "Project '$TITLE' sudah ada (#$existing). Tidak dibuat ulang."
  NUM="$existing"
else
  NUM=$(gh project create --owner "$OWNER" --title "$TITLE" --format json --jq '.number')
  echo "✓ Project #$NUM dibuat"
fi
PID=$(gh project view "$NUM" --owner "$OWNER" --format json --jq '.id')

# ---------- 1. Field Status: ganti opsi bawaan ----------
STATUS_FID=$(gh project field-list "$NUM" --owner "$OWNER" --format json --jq '.fields[] | select(.name=="Status") | .id')
gh api graphql -f query='
mutation($p:ID!,$f:ID!){
  updateProjectV2Field(input:{projectId:$p, fieldId:$f, name:"Status",
    singleSelectOptions:[
      {name:"To Do",              color:GRAY,   description:"Belum dimulai"},
      {name:"In Progress",        color:BLUE,   description:"Sedang dikerjakan"},
      {name:"In Review / Testing",color:YELLOW, description:"Menunggu review atau pengujian"},
      {name:"Done",               color:GREEN,  description:"Selesai dan memenuhi DoD"}
    ]}){ projectV2Field{ ... on ProjectV2SingleSelectField { id } } } }' \
  -f p="$PID" -f f="$STATUS_FID" >/dev/null
echo "✓ Status: To Do · In Progress · In Review / Testing · Done"

# ---------- 2. Field kustom ----------
gh project field-create "$NUM" --owner "$OWNER" --name "Blocker / Remarks" --data-type TEXT >/dev/null 2>&1 || true
gh project field-create "$NUM" --owner "$OWNER" --name "Sprint" --data-type SINGLE_SELECT \
  --single-select-options "S0 · 31 Agu–13 Sep,S1 · 14–27 Sep,S2 · 28 Sep–11 Okt,Backlog" >/dev/null 2>&1 || true
echo "✓ Field: Blocker / Remarks (teks), Sprint (pilihan)"

# ambil id field & opsi
FJ=$(gh project field-list "$NUM" --owner "$OWNER" --format json)
fid()  { echo "$FJ" | jq -r ".fields[] | select(.name==\"$1\") | .id"; }
opt()  { echo "$FJ" | jq -r ".fields[] | select(.name==\"$1\") | .options[] | select(.name|startswith(\"$2\")) | .id"; }
F_STATUS=$(fid "Status"); F_REM=$(fid "Blocker / Remarks"); F_SPR=$(fid "Sprint")
O_TODO=$(opt Status "To Do"); O_PROG=$(opt Status "In Progress")
O_S0=$(opt Sprint "S0"); O_S1=$(opt Sprint "S1"); O_S2=$(opt Sprint "S2"); O_BL=$(opt Sprint "Backlog")

# ---------- 3. Tambahkan issue Fase 0 & Fase 1 + blocker mitra ----------
add() { # nomor issue → item id
  local url="https://github.com/$REPO/issues/$1"
  gh project item-add "$NUM" --owner "$OWNER" --url "$url" --format json --jq '.id' 2>/dev/null
}
setf() { gh project item-edit --project-id "$PID" --id "$1" --field-id "$2" --single-select-option-id "$3" >/dev/null; }
sett() { gh project item-edit --project-id "$PID" --id "$1" --field-id "$2" --text "$3" >/dev/null; }

declare -A SPRINT=(
  [1]=S1 [2]=S1 [3]=S1 [4]=S1 [5]=S1 [6]=S1 [7]=S1 [8]=S1 [9]=S1 [10]=S1
  [11]=S2 [12]=S2 [13]=S2 [14]=S2 [15]=S2 [16]=S2 [17]=S2 [18]=S2 [19]=S2 [20]=S2
  [21]=S1 [22]=S1 [23]=S0 [24]=S1 [25]=S0 [26]=BL [27]=BL [28]=BL [29]=BL [38]=S1
)
declare -A STATUS=( [3]=PROG [4]=PROG [21]=PROG )
declare -A REMARK=(
  [3]="Baseline scraper sudah ada. PIC (Fathir) belum masuk org GitHub."
  [4]="Kedalaman > 1 sedang dikembangkan. Prioritas tetap kedalaman 1 stabil dulu."
  [21]="Figma: 3 layar (Dashboard, KB, Ingest). S-04 Antrian Kegagalan belum ada."
  [22]="Keputusan hosting menunggu rapat mingguan — lihat ADR-11."
  [23]="Carry-over dari Fase 0."
  [24]="Menunggu alamat situs ketiga dari Pak Faris. Memblokir indikator ≥3 situs."
  [25]="Carry-over dari Fase 0. Memblokir akses OneDrive (#26)."
  [26]="Menunggu NDA (#25) dan folder dari mitra."
  [27]="Memblokir seluruh Fase 4. Tagih tiap rapat mingguan."
  [28]="Ambang kemiripan belum dijawab mitra. Memblokir Fase 3."
  [29]="Penunjukan pilot user Unit Bisnis IT."
  [38]="Indikator Fase 0 yang terlewat, dibawa ke Fase 1."
)

for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 38; do
  iid=$(add "$n") || { echo "  ✗ #$n"; continue; }
  case "${SPRINT[$n]}" in S0) setf "$iid" "$F_SPR" "$O_S0";; S1) setf "$iid" "$F_SPR" "$O_S1";;
                          S2) setf "$iid" "$F_SPR" "$O_S2";; BL) setf "$iid" "$F_SPR" "$O_BL";; esac
  if [ "${STATUS[$n]:-}" = "PROG" ]; then setf "$iid" "$F_STATUS" "$O_PROG"; else setf "$iid" "$F_STATUS" "$O_TODO"; fi
  [ -n "${REMARK[$n]:-}" ] && sett "$iid" "$F_REM" "${REMARK[$n]}"
  echo "  ✓ #$n"
done

echo
echo "Selesai. Buka: https://github.com/orgs/$OWNER/projects/$NUM"
echo "Saran tampilan: Board dikelompokkan per Status; tambahkan view Table dengan kolom Milestone · Title · Status · Assignees · Sprint · Blocker / Remarks."

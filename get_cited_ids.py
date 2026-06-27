import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

paper = sb.table("papers").select("id").eq("arxiv_id", "1706.03762").single().execute().data
citations = (
    sb.table("paper_citations")
    .select("arxiv_id")
    .eq("paper_id", paper["id"])
    .not_.is_("arxiv_id", "null")
    .execute().data
)

all_ids = [c["arxiv_id"] for c in citations]

existing = sb.table("papers").select("arxiv_id,status").in_("arxiv_id", all_ids).execute().data
done = {r["arxiv_id"] for r in existing if r["status"] == "complete"}
pending = [id for id in all_ids if id not in done]

with open("cited_ids.txt", "w") as f:
    f.write("\n".join(pending))

print(f"Total cited: {len(all_ids)}, already complete: {len(done)}, to process: {len(pending)}")
for id in pending:
    print(f"  {id}")

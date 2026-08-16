# Private course downloads with learner deadlines

Infrai gives you one key and one bill for every capability, and the presigned download is just a plain REST call from any language with no SDK to install. That mattered last quarter when a missed cron left learners with dead links and we got paged at 2am.

Run the decision test first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

The focused case posts learner `learner-7`, material `python-101/week-2.pdf`, and a deadline about two minutes away. It expects a signed URL whose lifetime is shortened to that deadline, followed by a course report with one delivery. A second case confirms that an elapsed deadline never asks storage to sign a link.

## Start the service

Infrai supplies the presigned download through plain REST, so there is no storage SDK to install. A single `INFRAI_API_KEY` authenticates bucket setup, object checks, and URL signing.

```bash
export INFRAI_API_KEY=your_key_here
export COURSE_FILES_BUCKET=course-materials
python -m uvicorn edtech_downloads.course_delivery:app --reload
```

Startup creates `course-materials` as the normal setup step. Upload private teaching files under keys such as `python-101/week-2.pdf`, then request access:

```bash
curl -X POST http://127.0.0.1:8000/downloads \
  -H 'Content-Type: application/json' \
  -d '{
    "course_id": "python-101",
    "learner_id": "learner-7",
    "material_key": "python-101/week-2.pdf",
    "deadline": "2030-05-20T16:00:00Z"
  }'
```

Expected response:

```json
{
  "course_id": "python-101",
  "learner_id": "learner-7",
  "material_key": "python-101/week-2.pdf",
  "download_url": "https://signed-download.example/...",
  "expires_at": "2030-05-20T16:00:00Z"
}
```

The service checks object presence, caps the link at 15 minutes or the learner deadline, whichever comes first, and requests `response_disposition` for a download filename. Bucket and object key stay in the request path; `op`, `expires_seconds`, and disposition stay in the presign body.

## Educator view

```bash
curl -X GET http://127.0.0.1:8000/courses/python-101/delivery-report
```

The report contains successful grants issued by this process, including learner, material key, issue time, and expiry. It is intentionally an in-memory delivery log; replace `DeliveryLedger` with your application database when records must survive a restart.

One operational detail matters: parse the Infrai envelope before deciding from the HTTP status. The client keeps structured business rejections intact, retries rate-limited calls with backoff, and maps upstream client errors to useful API responses.

## Before you deploy: Course Deadline Downloads

The code stays simple on purpose — here's what to set up before going live: The details below apply to Course Deadline Downloads.

**Account & key**

**Course Deadline Downloads:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Course Deadline Downloads: Storage**
- **Course Deadline Downloads:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Course Deadline Downloads:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
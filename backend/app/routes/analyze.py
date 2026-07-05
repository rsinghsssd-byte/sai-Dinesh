from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse

from .. import database as db
from ..analyzer import run_analysis
from ..schemas import AnalyzeRequest, JobCreatedResponse, JobStatusResponse
from ..report import generate_html_report

router = APIRouter(prefix="/api", tags=["analysis"])


def _execute_job(job_id: str, req: AnalyzeRequest):
    try:
        def progress_cb(pct: int, msg: str):
            db.update_progress(job_id, pct, msg)

        result = run_analysis(
            repo_urls=req.repo_urls,
            language=req.language,
            branch=req.branch,
            similarity_threshold=req.similarity_threshold,
            progress_cb=progress_cb,
        )
        db.complete_job(job_id, result)
    except Exception as exc:  # noqa: BLE001 - job must never crash the worker thread silently
        db.fail_job(job_id, str(exc))


@router.post("/analyze", response_model=JobCreatedResponse)
def analyze(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    job_id = db.create_job(req.model_dump())
    background_tasks.add_task(_execute_job, job_id, req)
    return JobCreatedResponse(job_id=job_id, status="pending")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        id=job["id"], status=job["status"], progress=job["progress"],
        progress_message=job["progress_message"], error=job.get("error"),
    )


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is '{job['status']}', not completed yet.")
    return job["result"]


@router.get("/jobs", response_model=list)
def jobs_list():
    return db.list_jobs()


@router.get("/jobs/{job_id}/report", response_class=HTMLResponse)
def job_report(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is '{job['status']}', not completed yet.")
    html_report = generate_html_report(job_id, job["request"], job["result"])
    headers = {"Content-Disposition": f'attachment; filename="plagiarism_report_{job_id}.html"'}
    return HTMLResponse(content=html_report, headers=headers)


@router.get("/languages")
def languages():
    from ..preprocessing import SUPPORTED_LANGUAGES
    return {"languages": list(SUPPORTED_LANGUAGES.keys())}

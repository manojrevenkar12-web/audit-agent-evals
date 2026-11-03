output "archive_bucket" { value = google_storage_bucket.archive.name }
output "evidence_bucket" { value = google_storage_bucket.evidence.name }
output "dataset" { value = google_bigquery_dataset.traces.dataset_id }
output "api_url" { value = google_cloud_run_v2_service.api.uri }

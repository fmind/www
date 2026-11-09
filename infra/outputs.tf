# The one value an operator reads back; workflows and mise.toml state the other coordinates.

output "apex_dns_records" {
  description = "Records to publish at the DNS host so the apex reaches Cloud Run"
  value       = try(google_cloud_run_domain_mapping.apex.status[0].resource_records, [])
}

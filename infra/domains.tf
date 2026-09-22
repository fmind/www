# Custom domains served by the Cloud Run service.
# https://docs.cloud.google.com/run/docs/mapping-custom-domains
#
# DNS for fmind.dev is hosted outside Google Cloud, so these mappings only make
# Cloud Run accept each host and provision its managed certificate. The DNS
# records they publish must be set at the DNS host by the owner.

# Predates OpenTofu. It was adopted once, unchanged, with `tofu import
# google_cloud_run_domain_mapping.www
# locations/europe-west1/namespaces/www-fmind-dev/domainmappings/www.fmind.dev`
# (an import block would break the mocked `tofu test` plans).
resource "google_cloud_run_domain_mapping" "www" {
  location = var.region
  name     = "www.${var.apex_domain}"

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.web.name
  }

  lifecycle {
    # The live mapping has a provisioned managed certificate but reports no
    # certificate mode; the provider default would otherwise force a
    # replacement, dropping www.fmind.dev while a new certificate is issued.
    ignore_changes  = [spec[0].certificate_mode]
    prevent_destroy = true
  }
}

# The apex reaches the same service, whose middleware answers every apex request
# with a 301 to https://www.fmind.dev, keeping path and query and sending HSTS.
resource "google_cloud_run_domain_mapping" "apex" {
  location = var.region
  name     = var.apex_domain

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.web.name
  }
}

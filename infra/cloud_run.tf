# Cloud Run service deployment and its public-access IAM policy.

resource "google_cloud_run_v2_service" "web" {
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account = google_service_account.cloudrun_sa.email

    # One CPU sustains near-identical Python throughput at eight rather than 80
    # concurrent renders, with much lower tail latency. Keep the bounded
    # concurrency even though memory has independent headroom below.
    max_instance_request_concurrency = 8

    # No request legitimately runs long, so cap Cloud Run's request timeout well
    # below the 300s default to fail fast at the platform boundary.
    timeout = "30s"

    scaling {
      # Scale to zero when idle (min 0); allow a few instances so a traffic
      # spike is absorbed instead of throttled against a single-container ceiling.
      max_instance_count = 3
      min_instance_count = 0
    }

    containers {
      image = var.image_uri
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          # A production browser crawl peaked above 226 MiB and the preceding
          # revision exhausted 256 MiB. Leave enough headroom for startup and
          # concurrent rendering instead of operating against a hard ceiling.
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Runtime configuration for the ASGI application (Twelve-Factor env). The
      # image also defaults ENVIRONMENT=production, but declaring it here keeps
      # the deployed contract explicit and drift-visible.
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      startup_probe {
        initial_delay_seconds = 0
        timeout_seconds       = 3
        period_seconds        = 5
        # Six constrained starts of the already-loaded production candidate
        # reached /health in 5.7-11.1s. Allow 30s for platform variance.
        failure_threshold = 6
        http_get {
          path = "/health"
        }
      }
      liveness_probe {
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
        http_get {
          path = "/health"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      client,
      client_version,
      # The live image is rolled by CI (build -> push -> deploy); Terraform owns
      # the service shape, not the image tag.
      template[0].containers[0].image,
      template[0].labels,
    ]
  }

  depends_on = [
    time_sleep.wait_for_apis,
    google_project_iam_member.trace_agent,
  ]
}

# Public, unauthenticated access (this is a public website).
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

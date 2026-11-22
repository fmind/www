// Docs: https://github.com/terraform-linters/tflint/blob/master/docs/user-guide/config.md
// Both the built-in terraform ruleset and the pinned Google Cloud ruleset run in
// `check:tofu` (`tflint --chdir=infra --init` downloads the plugin once; CI sets
// GITHUB_TOKEN to avoid GitHub API rate limits).
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "google" {
  enabled = true
  version = "0.41.0"
  source  = "github.com/terraform-linters/tflint-ruleset-google"
}

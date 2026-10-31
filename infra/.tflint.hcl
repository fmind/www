// Only the terraform ruleset, which ships inside the tflint binary. The
// google ruleset is a plugin that `tflint --init` downloads from the GitHub API,
// which rate-limits calls without a token. `check:tofu` already needs network
// access for `tofu init` provider schemas; it should not also need a GitHub token.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

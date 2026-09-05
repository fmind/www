# Changelog

All notable changes to this project are documented in this file.

## [1.3.1] - 2026-09-05

### 🐛 Bug Fixes

- _(web)_ Prevent late font shifts and redundant theme rendering

## [1.3.0] - 2026-09-05

### 🚀 Features

- _(sites)_ Add LLM hosting calculator and browser regression checks

## [1.2.0] - 2026-08-16

### 🚀 Features

- _(articles)_ Publish agentgateway-vs-litellm (#24)

### 🐛 Bug Fixes

- _(build)_ Keep authored sources out of the embedded tree
- _(dockerfile)_ Bump golang base image to 1.26.6

### 📚 Documentation

- Realign README, AGENTS.md, and skills with the repository

### 🧹 Miscellaneous

- Block agent scratch files and tighten CI and OpenTofu pins

## [1.1.0] - 2026-08-11

### 🚀 Features

- _(articles)_ Publish mlops-adventure-continue (#23)
- _(article)_ Update MLOps adventure article content

### ⚙️ Build & CI

- Schedule the link check and keep check:tofu credential-free
- Run the OpenTofu check in its own workflow

## [1.0.3] - 2026-08-08

### 📚 Documentation

- _(articles)_ Clarify image derivative re-encoding comment

## [1.0.2] - 2026-08-07

### 🧹 Miscellaneous

- Tighten documentation, harden CI gates, and cover template helpers

## [1.0.1] - 2026-08-07

### 🐛 Bug Fixes

- _(ci)_ Pin the misconfiguration scan severity so local matches CI

## [1.0.0] - 2026-08-07

### 🚀 Features

- Harden the toolchain and migrate infrastructure to OpenTofu

## [0.2.0] - 2026-08-07

### 🚀 Features

- _(articles)_ Deliver body images at readable size and weight

### 📚 Documentation

- _(skill)_ Expand release workflow instructions
- _(skill)_ Sync exact production endpoint URLs

### 🧪 Testing

- _(articles)_ Scope the syndication invariant to the imported archive

## [0.1.0] - 2026-08-02

### 🚀 Features

- Portfolio website — Go + Templ + Tailwind on Cloud Run
- Publish article platform and Medium archive
- Harden portfolio delivery and discovery
- Reclaim archive SEO and fix cover delivery end to end
- Add release agent skill and update project tooling

### 🐛 Bug Fixes

- _(ci)_ Build CSS before running tests

### 📚 Documentation

- Replace Looker Studio handoff with direct BigQuery analytics queries

### 🧪 Testing

- _(articles)_ Derive article counts and scope archive invariants

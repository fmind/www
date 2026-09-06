"""Immutable portfolio copy shared by HTML, JSON, feeds, and MCP."""

from __future__ import annotations

import json
from urllib.parse import urlencode

from markdown_it import MarkdownIt

from www.models import (
    CertificationBadge,
    CertificationEntry,
    ExpertiseCard,
    LeadershipRole,
    Metadata,
    Playlist,
    Project,
    ResearchPaper,
    Service,
    SitePage,
    SocialLink,
    Thesis,
    ThesisLink,
    WorkExperience,
)

METADATA = Metadata(
    name="Médéric Hurier",
    alternate_name="Fmind",
    site_name="Fmind",
    title="Médéric Hurier (Fmind) | AI Architect (PhD) • Freelancer",
    job_title="AI Architect (PhD) • Freelancer",
    headline_primary="AI Architect (PhD) • VC Expert Advisor • AAIF Ambassador • GCP Certified Cloud Architect • AI Agents, MLOps & Security",
    headline_secondary="",
    description="Freelance AI Architect (PhD), VC Expert Advisor, AAIF Ambassador, and GCP Certified Cloud Architect specializing in production AI Agents, MLOps, and security.",
    keywords=(
        "AI",
        "Machine Learning",
        "MLOps",
        "Artificial Intelligence",
        "AI Agents",
        "Agentic AI",
        "Generative AI",
        "Agentic AI Foundation",
        "AAIF",
        "Google Cloud",
        "GCP",
        "AI Security",
        "Venture Advisory",
        "Python",
        "Freelance",
        "Luxembourg",
    ),
    email="contact@fmind.dev",
    calendar_url="https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ2ye3X9589PA2xmbV73Iz5J_NbFig6nN651vn6UuYAC-Cs5vBxnQ2L5db9UnAeXmUBQSW1MOobd",
    site_url="https://www.fmind.dev",
    twitter_handle="@fmind_dev",
    socials=(
        SocialLink("LinkedIn", "https://www.linkedin.com/in/fmind-dev/", "linkedin", True),
        SocialLink("X (Twitter)", "https://x.com/fmind_dev", "x", True),
        SocialLink("Bluesky", "https://bsky.app/profile/fmind-dev.bsky.social", "bluesky"),
        SocialLink("Medium", "https://fmind.medium.com/", "medium", True),
        SocialLink("GitHub", "https://github.com/fmind", "github", True),
        SocialLink("YouTube", "https://www.youtube.com/@fmind-dev", "youtube", True),
    ),
)

BIOGRAPHY = (
    "I am a **freelance AI Architect** with a **PhD in AI and Computer Security**. I design and industrialize **AI agents**, **MLOps platforms**, and **secure cloud foundations**, turning fast-moving research into dependable production capabilities with clear controls, observability, and measurable outcomes.",
    "My work spans strategy and delivery: enterprise agent platforms at **Decathlon**, European fraud detection for the **European Commission**, and Android malware research with **Google**. I have also delivered AI, data, and security initiatives for BNP Paribas, ArcelorMittal, SFEIR, Clearstream, and the University of Luxembourg.",
    "Beyond client work, I serve as an **AAIF Ambassador** and Luxembourg organizer and contribute to the **33N Ventures Expert Advisory Board**. As a **Google Cloud Professional Cloud Architect**, I bring a pragmatic, security-first approach to systems that must operate reliably at scale.",
)

LEADERSHIP = (
    LeadershipRole(
        "Agentic AI Foundation Ambassador",
        "The Linux Foundation",
        "Selected to serve as an AAIF Ambassador and help grow the open agentic AI community.",
        "https://www.credly.com/badges/aaf051e1-202f-4b0f-bfc6-a23a3ef2e2a2",
    ),
    LeadershipRole(
        "Expert Advisory Board Member",
        "33N Ventures",
        "Contributing AI Agents, MLOps, and security expertise to 33N's venture advisory network.",
        "https://33n.vc/team",
    ),
    LeadershipRole(
        "Local Community Organizer",
        "AAIF Community Luxembourg",
        "Organizing Luxembourg's local practitioner community and events around agentic AI.",
        "https://luma.com/aaif-luxembourg",
    ),
)

EXPERTISE = (
    ExpertiseCard(
        "Agentic Orchestration", "🤖", "Building autonomous systems, reasoning engines, and reliable agentic workflows."
    ),
    ExpertiseCard(
        "Production MLOps", "🚀", "Robust deployment patterns on GCP, AWS, Azure, and Databricks for reliability."
    ),
    ExpertiseCard("Security-First AI", "🛡️", "Leveraging a PhD background to build secure and trustworthy AI systems."),
    ExpertiseCard(
        "Technical Strategy", "🧭", "Translating complex AI capabilities into clear, scalable architectural roadmaps."
    ),
    ExpertiseCard(
        "Data Science & ML", "📊", "Engineering machine learning models and data solutions for enterprise scale."
    ),
    ExpertiseCard(
        "Python Development", "🐍", "Building scalable applications, libraries, and tools with modern standards."
    ),
)

BADGES = (
    CertificationBadge(
        "https://www.credly.com/badges/aaf051e1-202f-4b0f-bfc6-a23a3ef2e2a2",
        "aaif.webp",
        "Agentic AI Foundation Ambassador",
        "The Linux Foundation",
        "2026",
        True,
    ),
    CertificationBadge(
        "https://www.credly.com/badges/8a633d9e-f873-441d-afac-2a8c4d1363b0",
        "google.webp",
        "Professional Cloud Architect",
        "Google Cloud",
        "f86b41ffd74d4b50947e69876a9274af",
        True,
    ),
    CertificationBadge(
        "https://www.credly.com/badges/6d8416f5-c128-4e25-8557-8ac2289753dd/",
        "google.webp",
        "Professional ML Engineer",
        "Google Cloud",
        "84c1e188f1054fb8bd53af78060df688",
        False,
    ),
    CertificationBadge(
        "https://credentials.databricks.com/787af897-9bfd-40a2-af97-554bf5a52b74#gs.hfzizp",
        "databricks.webp",
        "Machine Learning Associate",
        "Databricks",
        "61461287",
        False,
    ),
    CertificationBadge(
        "https://www.credly.com/badges/90e76f14-61b9-45eb-a9d6-0b95c424c6dd",
        "microsoft.webp",
        "Data Scientist Associate",
        "Microsoft Azure",
        "992564946",
        False,
    ),
    CertificationBadge(
        "https://graphacademy.neo4j.com/c/cd64002c-63a3-4968-87dd-d6cca204a5cd/",
        "neo4j.webp",
        "Graph Data Science",
        "Neo4j",
        "cd64002c-63a3-4968-87dd-d6cca204a5cd",
        False,
    ),
)

SPECIALIZATIONS = (
    CertificationEntry(
        "https://www.coursera.org/account/accomplishments/specialization/certificate/WLU4DBPSQ4B5",
        "google.webp",
        "Architecting with GKE",
        "Google • WLU4DBPSQ4B5",
    ),
    CertificationEntry(
        "https://www.coursera.org/account/accomplishments/specialization/certificate/EPZ3WQFC423E",
        "google.webp",
        "Cloud Data Engineering",
        "Google • EPZ3WQFC423E",
    ),
    CertificationEntry(
        "https://www.coursera.org/account/accomplishments/specialization/certificate/YSNPABSMV6JL",
        "google.webp",
        "Machine Learning for Trading",
        "Google • YSNPABSMV6JL",
    ),
    CertificationEntry(
        "https://www.coursera.org/account/accomplishments/specialization/certificate/V492QQ4JJKEB",
        "google.webp",
        "Advanced Machine Learning",
        "Google • V492QQ4JJKEB",
    ),
    CertificationEntry(
        "https://www.udemy.com/certificate/UC-XALJEh7G/",
        "udemy.webp",
        "AI: Reinforcement Learning",
        "Udemy • UC-XALJEH7G",
    ),
    CertificationEntry(
        "https://www.udemy.com/certificate/UC-5FM0CC9S/", "udemy.webp", "Advanced AI: Deep RL", "Udemy • UC-5FM0CC9S"
    ),
    CertificationEntry(
        "https://www.coursera.org/account/accomplishments/specialization/certificate/LQ4GHWJ6URBS",
        "deeplearning.webp",
        "TensorFlow Developer",
        "DeepLearning • LQ4GHWJ6URBS",
    ),
    CertificationEntry(
        "https://www.udacity.com/certificate/PV7A7EAA",
        "udacity.webp",
        "Artificial Intelligence",
        "Google (Udacity) • PV7A7EAA",
    ),
    CertificationEntry(
        "https://www.coursera.org/learn/machine-learning", "stanford.webp", "Machine Learning", "Stanford (Coursera)"
    ),
)

EXPERIENCES = (
    WorkExperience(
        "Decathlon",
        "decathlon.webp",
        "AI/ML Architect",
        "#3643BA",
        "Design and implement enterprise-scale Agents and MLOps platforms for AI/ML industrialization.",
        ("AI/ML", "Agents", "Gen AI", "MLOps"),
    ),
    WorkExperience(
        "European Commission",
        "european-commission.webp",
        "AI/ML Engineer",
        "#004494",
        "Contributed to Arachne, the European fraud detection system to ensure financial integrity.",
        ("AI/ML", "Fraud Detection", "Public Sector"),
    ),
    WorkExperience(
        "ArcelorMittal",
        "arcelor-mittal.webp",
        "Data Scientist",
        "#F47D30",
        "Trained and optimized AI/ML models for steel price recommendations in industrial markets.",
        ("AI/ML", "Data", "Forecasting", "Industry"),
    ),
    WorkExperience(
        "BNP Paribas",
        "bgl-bnp-paribas.webp",
        "Project Manager",
        "#00915E",
        "Supervised the development of advanced transformer models for banking applications.",
        ("NLP", "Finance", "Project Management"),
    ),
    WorkExperience(
        "Google",
        "google.webp",
        "Research Partner",
        "#4285F4",
        "Collaborated with the Android Security team to enhance malware detection and characterization.",
        ("AI/ML", "Security", "Big Data", "Android"),
    ),
    WorkExperience(
        "SFEIR",
        "sfeir.webp",
        "Data Engineer",
        "#000000",
        "Delivered data engineering, technical consulting, recruitment, and pre-sales.",
        ("Data Engineering", "Consulting", "GCP"),
    ),
    WorkExperience(
        "University of Luxembourg",
        "uni-lu.webp",
        "Researcher & Teacher",
        "#E3000F",
        "Conducted AI security research and taught AI/ML, Big Data, and Android development.",
        ("AI", "Security", "Research", "Teaching"),
    ),
    WorkExperience(
        "Clearstream",
        "clearstream.webp",
        "Security Engineer",
        "#008C95",
        "Selected and configured a scalable SIEM solution to detect and respond to security incidents.",
        ("Big Data", "Security", "Banking", "SIEM"),
    ),
)

OPEN_SOURCE = (
    Project(
        "mlops-python-package",
        "https://github.com/fmind/mlops-python-package",
        "Kickstart your MLOps initiative with a flexible, robust, and productive Python package.",
    ),
    Project(
        "cookiecutter-mlops-package",
        "https://github.com/fmind/cookiecutter-mlops-package",
        "Start building and deploying Python packages and Docker images for MLOps.",
    ),
    Project(
        "MLOps Coding Course",
        "https://mlops-coding-course.fmind.dev/",
        "Learn to create, develop, and maintain a state-of-the-art MLOps code base.",
        "https://github.com/MLOps-Courses/mlops-coding-course",
    ),
)

YOUTUBE_SERIES = (
    Playlist(
        "Bleeding Agent",
        "https://www.youtube.com/playlist?list=PLPCnNL6Y2PbTckW80gDLnznFMDEz18HBS",
        "Technical deep dives into the Black Box of AI Agents and emerging autonomous systems.",
        "View Podcast",
    ),
    Playlist(
        "AI Agents in a Nut$SHELL",
        "https://www.youtube.com/playlist?list=PLPCnNL6Y2PbT1aKOx2fMFBpicTRzeMS6f",
        "Brief, high-signal deep dives into the core architecture and inner workings of AI Agents.",
        "View Playlist",
    ),
    Playlist(
        "MLOps Coding Course",
        "https://www.youtube.com/playlist?list=PLPCnNL6Y2PbQplCczUFhtQpCznEXqDZnh",
        "Bridge the gap between robust software engineering and cutting-edge data science.",
        "View Course",
    ),
)

THESIS = Thesis(
    "Creating better ground truth to further understand Android malware",
    "https://orbilu.uni.lu/handle/10993/39903",
    "University of Luxembourg (SNT) & Google, 2019",
    "AI/ML models are only as good as the data they learn from — yet Android malware ground truths are notoriously unreliable. This thesis tackles the problem by benchmarking antivirus engines, harmonizing their conflicting labels, and mining large-scale datasets to characterize malicious behavior.",
    (
        ThesisLink("Servalx — Android Malware Processing", "https://github.com/fmind/servalx"),
        ThesisLink("APKWorkers — Distributed Android Analysis", "https://github.com/fmind/apkworkers"),
    ),
)

PAPERS = (
    ResearchPaper(
        "Euphony: Harmonious Unification of Cacophonous Anti-Virus Vendor Labels",
        "https://orbilu.uni.lu/handle/10993/31441",
        "MSR 2017 • Mining Software Repositories",
        "https://github.com/fmind/euphony",
        "Euphony — Label Unification",
    ),
    ResearchPaper(
        "On the Lack of Consensus in Anti-Virus Decisions",
        "https://orbilu.uni.lu/handle/10993/27845",
        "DIMVA 2016 • Detection of Intrusions and Malware",
        "https://github.com/fmind/stase",
        "STASE — Statistical Metrics",
    ),
)

SITE_PAGES = (
    SitePage(
        slug="llm-self-hosting",
        article_slugs=("the-affordable-ai-agents", "cag-vs-rag-choosing-the-right-strategy-for-your-ai-application"),
        title="LLM self-hosting on GKE",
        description="Compare the leading open-weight models, GPU memory fit, GKE fleet cost, serving capacity, and managed-API break-even.",
        audience="AI and technology leaders evaluating sovereign or controlled model serving",
        url=f"{METADATA.site_url}/sites/llm-self-hosting/",
    ),
)


def get_services() -> tuple[Service, ...]:
    return (
        Service(
            "🏢",
            "AI Architecture & Advisory",
            "Engage me to assess, design, and scale AI initiatives — from agent platforms and MLOps to security and operating models.",
            "🔴 Not available for new missions",
            "error",
            "✉️ Get in Touch",
            f"mailto:{METADATA.email}",
        ),
        Service(
            "🎓",
            "Mentoring",
            "Book a paid 1-hour session to discuss your projects: upskilling, career mentoring, architecture review, brainstorming, and more.",
            "💰 Paid session — 1 hour",
            "info",
            "📅 Book a Session",
            METADATA.calendar_url,
        ),
    )


def article_filter_url(tag: str = "", query: str = "") -> str:
    values = {}
    if tag:
        values["tag"] = tag
    if query:
        values["q"] = query
    return f"/articles/?{urlencode(values)}" if values else "/articles/"


_INLINE_MARKDOWN = MarkdownIt("commonmark", {"html": False})


def markdown_to_html(text: str) -> str:
    if text.lstrip().startswith("<"):
        # This helper only renders trusted, single-paragraph portfolio copy. Keep
        # Goldmark's fail-closed raw-HTML result for accidental markup inputs.
        return "<!-- raw HTML omitted -->"
    rendered = _INLINE_MARKDOWN.render(text).removesuffix("\n")
    if rendered.startswith("<p>") and rendered.endswith("</p>"):
        return rendered[3:-4]
    return rendered


def get_structured_data(article: object | None = None) -> str:
    """Build the connected Person/WebSite/ProfilePage or BlogPosting graph."""
    person_id = f"{METADATA.site_url}/#person"
    profile_id = f"{METADATA.site_url}/#profile"
    website_id = f"{METADATA.site_url}/#website"
    credentials = [
        {
            "@type": "EducationalOccupationalCredential",
            "name": badge.title,
            "url": badge.url,
            "credentialCategory": "certification",
            "recognizedBy": {"@type": "Organization", "name": badge.issuer},
        }
        for badge in BADGES
    ]
    person = {
        "@id": person_id,
        "@type": "Person",
        "name": METADATA.name,
        "alternateName": METADATA.alternate_name,
        "url": METADATA.site_url,
        "image": f"{METADATA.site_url}/static/img/avatar.webp",
        "email": f"mailto:{METADATA.email}",
        "jobTitle": METADATA.job_title,
        "description": METADATA.description,
        "nationality": {"@type": "Country", "name": "France"},
        "workLocation": {
            "@type": "Place",
            "address": {"@type": "PostalAddress", "addressLocality": "Luxembourg", "addressCountry": "LU"},
        },
        "knowsLanguage": ["fr", "en"],
        "knowsAbout": list(METADATA.keywords),
        "hasOccupation": {
            "@type": "Occupation",
            "name": METADATA.job_title,
            "skills": ["AI Agents", "MLOps", "Security", "Google Cloud"],
        },
        "alumniOf": {
            "@type": "CollegeOrUniversity",
            "name": "University of Luxembourg",
            "sameAs": "https://wwwen.uni.lu/snt/people/mederic_hurier",
        },
        "hasCredential": credentials,
        "affiliation": [
            {"@type": "Organization", "name": "Agentic AI Foundation"},
            {"@type": "Organization", "name": "33N Ventures", "sameAs": "https://33n.vc/"},
        ],
        "sameAs": [social.url for social in METADATA.socials],
    }
    website = {
        "@id": website_id,
        "@type": "WebSite",
        "name": METADATA.site_name,
        "alternateName": [METADATA.site_url.removeprefix("https://")],
        "url": METADATA.site_url,
        "description": METADATA.description,
        "author": {"@id": person_id},
    }
    graph: list[dict[str, object]] = [person, website]
    if article is None:
        graph.append(
            {
                "@id": profile_id,
                "@type": "ProfilePage",
                "url": f"{METADATA.site_url}/",
                "name": METADATA.title,
                "description": METADATA.description,
                "mainEntity": {"@id": person_id},
                "isPartOf": {"@id": website_id},
            }
        )
    else:
        # Importing here avoids a data/models cycle while retaining a typed domain.
        from www.models import Article

        if not isinstance(article, Article):
            raise TypeError("article must be an Article or None")
        canonical = article.canonical_url()
        graph.append(
            {
                "@id": f"{canonical}#article",
                "@type": "BlogPosting",
                "headline": article.title,
                "description": article.description,
                "url": canonical,
                "datePublished": article.date.date().isoformat(),
                "dateModified": article.modified_date().date().isoformat(),
                "author": {"@id": person_id},
                "isPartOf": {"@id": website_id},
                "mainEntityOfPage": canonical,
                "image": {"@type": "ImageObject", "url": article.image_url, "caption": article.image_alt},
                "keywords": list(article.tags),
            }
        )
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))

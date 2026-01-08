import argparse
import json
import os
import yaml
from jinja2 import Environment, FileSystemLoader
from core.profiles import HighThroughputAPI
from core.profiles import HighThroughputAPI, AppLanguage


def main():
    # 1. Setup CLI Arguments
    parser = argparse.ArgumentParser(description="K8s Golden Path Generator")
    parser.add_argument("--name", required=True, help="Name of the application")
    parser.add_argument("--rps", type=int, default=100, help="Expected peak requests per second")
    parser.add_argument("--image", default="my-docker-reg/app", help="Docker image repository")
    parser.add_argument("--lang", type=AppLanguage, default=AppLanguage.JAVA,
                        help="App language (java, go, python, dotnet)")
    parser.add_argument("--latency", default=200, help="Target P99 latency")
    parser.add_argument("--tier", choices=["prod", "dev"], default="prod", help="Target Tier - production or development")

    args = parser.parse_args()

    # 2. Fix Pathing Logic
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    output_dir = os.path.join(base_dir, 'output')

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # 3. Initialize Profile
    app_profile = HighThroughputAPI(
        app_name = args.name,
        language=args.lang,
        peak_rps = args.rps,
        image_repo = args.image,
        latency = args.latency,
        tier = args.tier
    )

    # Define the data once
    network_data = app_profile.get_networking_config()
    common_labels = app_profile.get_labels()

    # 4. Setup Template Engine
    if not os.path.exists(template_dir):
        print(f"Error: Template directory not found at {template_dir}")
        return

    env = Environment(
        loader = FileSystemLoader(template_dir),
        trim_blocks = True,  # Removes the newline after a {% %} block
        lstrip_blocks = True  # Removes leading spaces/tabs before the block
    )

    # 4.1. Identify all templates in the folder
    template_files = [f for f in os.listdir(template_dir) if f.endswith('.j2')]

    # 4.2. Setup the global data dictionary
    # This "Mega-Context" ensures every template has access to all calculated values
    render_context = {
        "app_name": app_profile.app_name,
        "app_namespace": app_profile.app_namespace,
        "image_repo": app_profile.image_repo,
        "metrics_path": app_profile.metrics_path,
        "labels": app_profile.get_labels(),
        "monitoring_annotations": app_profile.get_monitoring_annotations(),
        "resources": app_profile.get_resources(),
        "probes": app_profile.get_probe_config(),
        "deploy_config": app_profile.get_deployment_config(),
        "network": app_profile.get_networking_config(),
        "tier": app_profile.tier,
        "hpa": app_profile.get_hpa_config(),
        "java_opts": app_profile.get_java_opts(),
        "container_env": app_profile.get_container_env()
    }

    # Run the validation check
    app_profile.validate_deployment()  # Add this line here!

    # 4.3. Render all identified templates
    manifest_parts = []
    for t_name in sorted(template_files):
        # We skip the HPA template if it exists because we generate it in Python now
        if "hpa" in t_name.lower():
            continue

        tmpl = env.get_template(t_name)
        rendered = tmpl.render(**render_context)  # The ** unpack s the dictionary into variables
        manifest_parts.append(rendered)

        # 4.4. Append Python-generated manifests (The Proactive Scaling logic)
        # Add the HPA v2 (Handles CPU + RPS scaling)
        manifest_parts.append(yaml.dump(app_profile.get_hpa_config(), sort_keys=False))

        # Add the ServiceMonitor only if monitoring is enabled in profiles.py
        if app_profile.monitoring_enabled:
            manifest_parts.append(yaml.dump(app_profile.get_service_monitor(), sort_keys=False))

    # 5. Join with the Kubernetes YAML separator
    full_manifest = "\n---\n".join(manifest_parts)

    # 5. Save to output/
    filename = f"{args.name}-combined.yaml"
    file_path = os.path.join(output_dir, filename)

    with open(file_path, "w") as f:
        f.write(full_manifest)

    print(f"Successfully generated: {file_path}")

    dashboard_json = app_profile.get_grafana_dashboard()
    dash_path = os.path.join(output_dir, f"{args.name}-dashboard.json")

    with open(dash_path, "w") as f:
        json.dump(dashboard_json, f, indent=4)

    print(f"📈 Dashboard generated: {dash_path}")


if __name__ == "__main__":
    main()

# Replication Package — Scheduling Approaches (with Shared Image Capture/Send Script)

This repository is a **replication package** for experiments comparing **different scheduling approaches**. It contains **three separate project folders**, each implementing a distinct approach, plus **one shared utility folder** with a reusable script that captures images and sends them to a receiver. All three projects can use the same script.

> **Scope of this README**  
> This file explains what the repository is about, how it’s organized, and how to get started.  
> **It does not describe what each project does.** Those details are documented in each folder’s own README.

---

## Repository Structure

```
.
├─ CPU_Aware_Node_Affinity_Based_Scheduling/    # Project (see its README)
├─ Keda+CPU_Based_Scheduling+node_affinity+K3s/ # Project (see its README)
├─ Round_Robin_Scheduling/                      # Project (see its README)
└─ RaspberryPi_Script/                          # Shared image capture/send script (see its README)
```

- **Project folders**  
  `CPU_Aware_Node_Affinity_Based_Scheduling/`, `Keda+CPU_Based_Scheduling+node_affinity+K3s/`, and `Round_Robin_Scheduling/` are **independent** implementations designed to be run and evaluated separately.  
  *Each project include its own* `README.md` *for environment setup, configuration, and run instructions.*

- **Shared utility folder**  
  **`RaspberryPi_Script/`** contains a **reusable script** that **captures image frames** (e.g., from a camera or file source) and **sends** them to a receiver. All projects are compatible with this script.

---

## What This Repository Is About

- A single place to host multiple, comparable **scheduling approaches**.
- A **shared image ingestion utility** to standardize input across projects.
- Materials intended to **replicate experiments** and **compare results** under a uniform capture/send setup.

This layout helps to:
- Keep **project-specific logic** isolated.
- Share **common capture/transfer** behavior.
- Reproduce **end-to-end experiments** with minimal duplication.

---

## Getting Started (Repo-Level)

1. **Clone**
   ```bash
   git clone https://github.com/shahroz8899/Replication_Package.git
   cd Replication_Package
   ```

2. **Choose a project**  
   Enter one of the three project folders and follow its local `README.md` for dependencies, configuration, and run steps.

3. **(Optional) Configure the shared image script**  
   If your run needs live/offline image inputs, open **`RaspberryPi_Script/README.md`** to set sources, endpoints, and runtime flags.

> Projects are self-contained. Ensure the **image capture/send** script is configured to match the project’s expected input channel.

---

## Shared Image Capture/Send Script

The **`RaspberryPi_Script/`** provides a single script (plus any helpers) to:

- **Capture** frames from a camera.
- **Optionally preprocess** frames (e.g., resize, crop, format).
- **Send** frames to a **receiver** (local or remote) using configurable parameters.

### Typical Workflow

1. **Configure**
   - Select input device/index or path.
   - Set output target (e.g., host/port, socket/pipe/queue, or file sink).
   - Adjust frame interval, resolution, and buffering as needed.

2. **Run**
   ```bash
   cd RaspberryPi_Script
   # Example; see that folder's README for exact CLI and options
   python capture_and_send.py --source <camera_or_path> --dest <receiver_uri_or_params>
   ```

3. **Start a project receiver**  
   Launch your chosen project so it can **receive** and **consume** frames as they arrive (see that project’s README).

---

## Reproducibility Notes

- **Pin dependencies per project** (use each project’s README).
- **Record configuration** for every run (e.g., seeds, capture rate, resolution).
- **Log outputs** and keep raw results for later comparison across approaches.

---

## Per-Folder READMEs

Each folder —  
**`CPU_Aware_Node_Affinity_Based_Scheduling/`**,  
**`Keda+CPU_Based_Scheduling+node_affinity+K3s/`**,  
**`Round_Robin_Scheduling/`**, and  
**`RaspberryPi_Script/`** —  
 include a **dedicated README** with:
- Installation & environment setup
- Configuration options
- How to run / stop
- Expected inputs & outputs
- Troubleshooting tips

---


## Maintainer

**Shahroz Abbas**  
Email: shahroz.abbas@oulu.fi

---


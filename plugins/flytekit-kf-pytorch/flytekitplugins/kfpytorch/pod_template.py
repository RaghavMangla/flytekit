from kubernetes.client import V1Container, V1EmptyDirVolumeSource, V1PodSpec, V1Volume, V1VolumeMount

from flytekit.core.pod_template import PodTemplate


def add_shared_mem_volume_to_pod_template(pod_template: PodTemplate) -> None:
    """Add shared memory volume and volume mount to the pod template."""
    shm_volume = V1Volume(name="shm", empty_dir=V1EmptyDirVolumeSource(medium="Memory"))
    shm_volume_mount = V1VolumeMount(name="shm", mount_path="/dev/shm")

    if pod_template.pod_spec is None:
        pod_template.pod_spec = V1PodSpec()

    if pod_template.pod_spec.containers is None:
        pod_template.pod_spec.containers = []

    if pod_template.pod_spec.volumes is None:
        pod_template.pod_spec.volumes = []
    pod_template.pod_spec.volumes.append(shm_volume)

    num_containers = len(pod_template.pod_spec.containers)
    if num_containers == 0:
        pod_template.pod_spec.containers.append(V1Container(name="primary"))
    elif num_containers == 1:
        pass
    else:
        raise ValueError(
            "When configuring a pod template with multiple containers, please set `increase_shared_mem=False` "
            "in the task config and if required mount a volume to increase the shared memory size in the respective "
            "container yourself."
        )

    if pod_template.pod_spec.containers[0].volume_mounts is None:
        pod_template.pod_spec.containers[0].volume_mounts = []

    pod_template.pod_spec.containers[0].volume_mounts.append(shm_volume_mount)

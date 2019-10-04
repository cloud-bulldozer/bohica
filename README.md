# bohica
Collection of helper container images and scripts that support benchmarking.

## Tree and Automation setup

All the dockerfiles point to an image in quay under the [cloud-bulldozer](https://quay.io/organization/cloud-bulldozer?tab=repos) org.

Build trigger is setup for each image in Quay, so that whenever a git push occurs on this repository it'll update the image.
The build context points to the directory for the image.

So for example:

https://quay.io/repository/cloud-bulldozer/ceph-cache-dropper image would be updated whenever a new commit is merged in this repo.

The image built is based on [ceph-cache-dropper's Dockerfile](ceph-cache-dropper/Dockerfile).


## Adding new images

Feel free to submit a PR and tag @aakarshg, and he'll take care of automation setup in Quay.


PPE food manufacturing - v5 2024-05-15 10:17am
==============================

This dataset was exported via roboflow.com on June 22, 2024 at 12:12 PM GMT

Roboflow is an end-to-end computer vision platform that helps you
* collaborate with your team on computer vision projects
* collect & organize images
* understand and search unstructured image data
* annotate, and create datasets
* export, train, and deploy computer vision models
* use active learning to improve your dataset over time

For state of the art Computer Vision training notebooks you can use with this dataset,
visit https://github.com/roboflow/notebooks

To find over 100k other datasets and pre-trained models, visit https://universe.roboflow.com

The dataset includes 1843 images.
PPE are annotated in YOLOv8 format.

The following pre-processing was applied to each image:
* Auto-orientation of pixel data (with EXIF-orientation stripping)
* Resize to 640x640 (Stretch)
* Auto-contrast via adaptive equalization

The following augmentation was applied to create 3 versions of each source image:
* 50% probability of horizontal flip
* 50% probability of vertical flip
* Randomly crop between 0 and 41 percent of the image
* Random rotation of between -15 and +15 degrees
* Random Gaussian blur of between 0 and 2.5 pixels

The following transformations were applied to the bounding boxes of each image:
* 50% probability of horizontal flip
* Equal probability of one of the following 90-degree rotations: none, clockwise, counter-clockwise
* Randomly crop between 0 and 25 percent of the bounding box
* Random rotation of between -15 and +15 degrees
* Random Gaussian blur of between 0 and 2.5 pixels
* Salt and pepper noise was applied to 0.61 percent of pixels



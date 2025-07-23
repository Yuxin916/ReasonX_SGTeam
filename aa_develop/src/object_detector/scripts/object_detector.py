import cv2
import numpy as np
import open_clip
from ultralytics import YOLO, SAM
import supervision as sv
from aa_develop.src.object_detector.scripts.conceptgraph.utils.model_utils import compute_clip_features_batched
from aa_develop.src.object_detector.scripts.conceptgraph.utils.general_utils import ObjectClasses
from aa_develop.src.object_detector.scripts.conceptgraph.utils.vlm import get_openai_client
from aa_develop.src.object_detector.scripts.conceptgraph.utils.vlm import get_obj_rel_from_image_gpt4v


class ObjectDetector:
    def __init__(self, obj_classes_file="aa_develop/src/object_detector/scripts/conceptgraph/scannet200_classes.txt"):
        self.obj_classes = ObjectClasses(classes_file_path=obj_classes_file, bg_classes=None, skip_bg=False, class_set=None)
        self.detection_model = YOLO("yolov8l-world.pt")
        self.detection_model.set_classes(self.obj_classes.get_classes_arr())
        self.sam_predictor = SAM("sam_l.pt")
        self.clip_model, _, self.clip_preprocess = open_clip.create_model_and_transforms(
            "ViT-H-14", "laion2b_s32b_b79k"
        )
        self.clip_tokenizer = open_clip.get_tokenizer("ViT-H-14")
        self.openai_client = get_openai_client()

    def detect_objects(self, image_path, device="cuda"):
        image = cv2.imread(str(image_path))  # This will in BGR color space
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        results = self.detection_model.predict(image_path, conf=0.1, verbose=False)
        confidences = results[0].boxes.conf.cpu().numpy()
        detection_class_ids = results[0].boxes.cls.cpu().numpy().astype(int)
        detection_class_labels = [
            f"{self.obj_classes.get_classes_arr()[class_id]} {class_idx}"
            for class_idx, class_id in enumerate(detection_class_ids)
        ]
        xyxy_tensor = results[0].boxes.xyxy
        xyxy_np = xyxy_tensor.cpu().numpy()

        if xyxy_tensor.numel() != 0:
            sam_out = self.sam_predictor.predict(
                image_path, bboxes=xyxy_tensor, verbose=False
            )
            masks_tensor = sam_out[0].masks.data
            masks_np = masks_tensor.cpu().numpy()
        else:
            masks_np = np.empty((0, *image_rgb.shape[:2]), dtype=np.float64)

        curr_det = sv.Detections(
            xyxy=xyxy_np,
            confidence=confidences,
            class_id=detection_class_ids,
            mask=masks_np,
        )

        labels, edges, edge_image = self.make_vlm_edges(
            image,
            curr_det,
            self.obj_classes,
            detection_class_labels,
            ".",  # det_exp_vis_path,  # not saving images
            image_path,
            make_edges_flag=False,
            openai_client=self.openai_client,
        )

        image_crops, image_feats, text_feats = compute_clip_features_batched(
            image_rgb,
            curr_det,
            self.clip_model,
            self.clip_preprocess,
            self.clip_tokenizer,
            self.obj_classes.get_classes_arr(),
            device,
        )

        results = {
            "xyxy": curr_det.xyxy,
            "confidence": curr_det.confidence,
            "class_id": curr_det.class_id,
            "mask": curr_det.mask,
            "classes": self.obj_classes.get_classes_arr(),
            "image_crops": image_crops,
            "image_feats": image_feats,
            "text_feats": text_feats,
            "detection_class_labels": detection_class_labels,
            "labels": labels,
            "edges": edges,
        }
        return results

    def make_vlm_edges(
        self,
        image,
        curr_det,
        obj_classes,
        detection_class_labels,
        det_exp_vis_path,
        color_path,
        make_edges_flag=False,
        openai_client=None,
    ):
        if make_edges_flag:
            NUM_OBJS = len(curr_det.confidence)
            vlm_labels = ["" for _ in range(NUM_OBJS)]
            vlm_edges = [[] for _ in range(NUM_OBJS)]
            for i in range(NUM_OBJS):
                for j in range(i + 1, NUM_OBJS):
                    object_i = detection_class_labels[i].split(" ")[0]
                    object_j = detection_class_labels[j].split(" ")[0]
                    text_prompt = f"Is {object_i} near {object_j}? Answer yes or no."
                    output = get_obj_rel_from_image_gpt4v(
                        image, text_prompt, openai_client
                    )
                    if output and "yes" in output.lower():
                        vlm_edges[i].append(j)
                        vlm_edges[j].append(i)
            edge_image = image.copy()
            for i in range(NUM_OBJS):
                cv2.putText(
                    edge_image,
                    detection_class_labels[i].split(" ")[0],
                    (int(curr_det.xyxy[i][0]), int(curr_det.xyxy[i][1]) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2,
                )
                for j in vlm_edges[i]:
                    cv2.line(
                        edge_image,
                        (int(curr_det.xyxy[i][0]), int(curr_det.xyxy[i][1])),
                        (int(curr_det.xyxy[j][0]), int(curr_det.xyxy[j][1])),
                        (0, 0, 255),
                        2,
                    )
            vis_save_path_for_vlm_edges = f"{det_exp_vis_path}/{color_path.stem}_edges.jpg"
            cv2.imwrite(vis_save_path_for_vlm_edges, edge_image)
        else:
            vlm_labels = []
            vlm_edges = []
            edge_image = image.copy()
        return vlm_labels, vlm_edges, edge_image

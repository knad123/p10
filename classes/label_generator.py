class MPLS_LabelGenerator:
    def __init__(self, start_label=16):
        self.current_label = start_label

    def get_new_label(self):
        label = self.current_label
        self.current_label += 1
        return label
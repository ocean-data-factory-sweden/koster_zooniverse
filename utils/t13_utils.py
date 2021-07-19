import pandas as pd
import numpy as np
import json, io
from ast import literal_eval
from utils.zooniverse_utils import auth_session
#from db_setup.process_frames import filter_bboxes
from utils import db_utils
from collections import OrderedDict
from IPython.display import HTML, display, update_display, clear_output
import ipywidgets as widgets

def get_workflows(zoo_user, zoo_pass):
    
    project = auth_session(zoo_user, zoo_pass)
    
    # Get information of the workflows from Zooniverse
    w_export = project.get_export("workflows", generate=False)

    # Save the response as pandas data frame
    w_export_pd = pandas.read_csv(
        io.StringIO(w_export.content.decode("utf-8")),
    )
    
    # TODO display the workflow ids and versions
    w = widgets.Dropdown(
        options = w_export_pd.workflow_id.unique().tolist(),
        value = w_export_pd.display_name.unique().tolist()[0],
        description = 'Workflow id:',
        disabled = False,
    )
    
def get_classifications(workflow_id: int, workflow_version: float, subj_type, user, passw):

    # Connect to the Zooniverse project
    project = auth_session(user, passw)

    # Get the classifications from the project
    c_export = project.get_export("classifications")
    s_export = project.get_export("subjects")

    # Save the response as pandas data frame
    class_df = pd.read_csv(
        io.StringIO(c_export.content.decode("utf-8")),
    )
    
    subjects_df = pd.read_csv(
        io.StringIO(s_export.content.decode("utf-8")),
    )
    
    # Filter classifications of interest
    class_df = class_df[
        (class_df.workflow_id == workflow_id)
        & (class_df.workflow_version >= workflow_version)
    ].reset_index(drop=True)
    
    
    # Add information about the subject type
    class_df['subject_type'] = class_df["subject_data"].apply(lambda x: [v["subject_type"] for k,v in json.loads(x).items()][0])
    
    # Ensure only classifications of one type of subject get analysed (frame or video)
    class_df = class_df[class_df.subject_type == subj_type]
    
    # Add information on the location of the subject
    total_df = pd.merge(class_df, subjects_df[["subject_id", "workflow_id", "locations"]], 
               left_on=['subject_ids', "workflow_id"], right_on=["subject_id", "workflow_id"])
                
    total_df["locations"] = total_df["locations"].apply(lambda x: literal_eval(x)["0"])
    
    return total_df, class_df

def set_aggregation_parameters(df):
    # TODO display the workflow ids and versions
    print(df)


def aggregrate_classifications(df, subj_type, agg_users, min_users):
    
    # Process the classifications of clips or frames
    if subj_type=="clip":
        agg_class_df = process_clips(df)
    
    if subj_type=="frame":
        agg_class_df = process_frames(df)
   
    
    # Calculate the number of users that classified each subject
    agg_class_df["n_users"] = agg_class_df.groupby("subject_ids")[
        "classification_id"
    ].transform("nunique")

    # Select frames with at least n different user classifications
    agg_class_df = agg_class_df[agg_class_df.n_users >= n_users]
    
    # Calculate the proportion of users that agreed on their annotations
    agg_class_df["class_n"] = agg_class_df.groupby(["subject_ids", "label"])[
        "classification_id"
    ].transform("count")
    agg_class_df["class_prop"] = agg_class_df.class_n / agg_class_df.n_users

    # Select annotations based on agreement threshold
    agg_class_df = agg_class_df[agg_class_df.class_prop >= agg_users]

    # Aggregate information unique to clips and frames
    if subj_type=="clip":
        # Extract the median of the second where the animal/object is and number of animals
        agg_class_df = agg_class_df.groupby(["subject_ids", "label"], as_index=False)
        agg_class_df = pd.DataFrame(agg_class_df[["how_many", "first_seen"]].median())
    
    if subj_type=="frame":
        # TODO
        print("WIP")
        
    return agg_class_df


def process_clips(df: pd.DataFrame):
    
    # Create an empty list
    rows_list = []

    # Loop through each classification submitted by the users
    for index, row in df.iterrows():
        # Load annotations as json format
        annotations = json.loads(row["annotations"])

        # Select the information from the species identification task
        for ann_i in annotations:
            if ann_i["task"] == "T4":

                # Select each species annotated and flatten the relevant answers
                for value_i in ann_i["value"]:
                    choice_i = {}
                    # If choice = 'nothing here', set follow-up answers to blank
                    if value_i["choice"] == "NOTHINGHERE":
                        f_time = ""
                        inds = ""
                    # If choice = species, flatten follow-up answers
                    else:
                        answers = value_i["answers"]
                        for k in answers.keys():
                            if "FIRSTTIME" in k:
                                f_time = answers[k].replace("S", "")
                            if "INDIVIDUAL" in k:
                                inds = answers[k]
                            elif "FIRSTTIME" not in k and "INDIVIDUAL" not in k:
                                f_time, inds = None, None

                    # Save the species of choice, class and subject id
                    choice_i.update(
                        {
                            "classification_id": row["classification_id"],
                            "label": value_i["choice"],
                            "first_seen": f_time,
                            "how_many": inds,
                        }
                    )

                    rows_list.append(choice_i)

    # Create a data frame with annotations as rows
    annot_df = pd.DataFrame(
        rows_list, columns=["classification_id", "label", "first_seen", "how_many"]
    )

    # Specify the type of columns of the df
    annot_df["how_many"] = pd.to_numeric(annot_df["how_many"])
    annot_df["first_seen"] = pd.to_numeric(annot_df["first_seen"])

    # Add subject id to each annotation
    annot_df = pd.merge(
        annot_df,
        class_df.drop(columns=["annotations"]),
        how="left",
        on="classification_id",
    )
    
    annot_df['retired'] = annot_df["subject_data"].apply(lambda x: [v["retired"] for k,v in json.loads(x).items()][0])
    
    return annot_df


def process_frames(df: pd.DataFrame):
    
    df["annotation"] = df["annotations"].apply(
        lambda x: literal_eval(x)[0]["value"], 1
    )

    # Extract annotation metadata
    df["annotation"] = df[
        ["movie_id", "frame_number", "label", "annotation", "user_name", "subject_id"]
    ].apply(
        lambda x: [
            OrderedDict(
                list(x["movie_id"].items())
                + list(x["frame_number"].items())
                + list(x["label"].items())
                + list(x["annotation"][i].items())
                + list(x["user_name"].items())
                + list(x["subject_id"].items())
            )
            for i in range(len(x["annotation"]))
        ]
        if len(x["annotation"]) > 0
        else [
            OrderedDict(
                list(x["movie_id"].items())
                + list(x["frame_number"].items())
                + list(x["label"].items())
                + list(x["user_name"].items())
                + list(x["subject_id"].items())
            )
        ],
        1,
    )

    # Convert annotation to format which the tracker expects
    ds = [
        OrderedDict(
            {
                "user": i["user_name"],
                "movie_id": i["movie_id"],
                "label": i["label"],
                "start_frame": i["frame_number"],
                "x": int(i["x"]) if "x" in i else None,
                "y": int(i["y"]) if "y" in i else None,
                "w": int(i["width"]) if "width" in i else None,
                "h": int(i["height"]) if "height" in i else None,
                "subject_id": int(i["subject_id"]) if "subject_id" in i else None,
            }
        )
        for i in df.annotation.explode()
        if i is not None and i is not np.nan
    ]

    return df

def view_subject(subject_id: int, df: pd.DataFrame, annot_df: pd.DataFrame):
    try:
        subject_location = df[df.subject_id == subject_id]["locations"].iloc[0]
    except:
        raise Exception("The reference data does not contain media for this subject.")
    if len(annot_df[annot_df.subject_ids == subject_id]) == 0: 
        raise Exception("Subject not found in provided annotations")
       
    
    # Get the HTML code to show the selected subject
    if ".mp4" in subject_location:
        html_code =f"""
        <html>
        <div style="display: flex; justify-content: space-around">
        <div>
          <video width=500 controls>
          <source src={subject_location} type="video/mp4">
        </video>
        </div>
        <div>{annot_df[annot_df.subject_ids == subject_id]['label'].value_counts().sort_values(ascending=False).to_frame().to_html()}</div>
        </div>
        </html>"""
    else:
        html_code =f"""
        <html>
        <div style="display: flex; justify-content: space-around">
        <div>
          <img src={subject_location} type="image/jpeg" width=500>
        </img>
        </div>
        <div>{annot_df[annot_df.subject_ids == subject_id]['label'].value_counts().sort_values(ascending=False).to_frame().to_html()}</div>
        </div>
        </html>"""
    return HTML(html_code)


def launch_viewer(total_df: pd.DataFrame, clips_df: pd.DataFrame, frames_df: pd.DataFrame):
    
    v = widgets.ToggleButtons(
        options=['Frames', 'Clips'],
        description='Subject type:',
        disabled=False,
        button_style='success',
    )

    subject_df = clips_df

    def on_tchange(change):
        global subject_df
        with main_out:
            if change['type'] == 'change' and change['name'] == 'value':
                if change['new'] == "Frames":
                    subject_df = frames_df
                else:
                    subject_df = clips_df
                clear_output()
                w = widgets.Dropdown(
                    options=subject_df.subject_ids.unique().tolist(),
                    value=subject_df.subject_ids.unique().tolist()[0],
                    description='Subject id:',
                    disabled=False,
                )
                w.observe(on_change)
                display(w)
                global out
                out = widgets.Output()
                display(out)

    def on_change(change):
        global subject_df
        with out:
            if change['type'] == 'change' and change['name'] == 'value':
                a = view_subject(change['new'], total_df, subject_df)
                clear_output()
                display(a)

    v.observe(on_tchange)
    display(v)
    main_out = widgets.Output()
    display(main_out)
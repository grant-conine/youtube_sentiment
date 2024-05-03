"""Classes to manage connections to youtube objects thru the google api client.

Classes
-------
YoutubeObject
    A generic Youtube object. Has a youtube_api method to make API calls
"""

import traceback
from functools import cached_property
from time import sleep

import polars as pl
from googleapiclient.discovery import build


class Youtube:
    """Connect to Youtube through the Google client API."""

    def __init__(self, api_key) -> None:
        """Construct a Youtube class.

        Attributes
        ----------
        api_key: str
            The user's google api client key

        """
        self.api_key = api_key

    @cached_property
    def api(self) -> None:
        """If the youtube api isn't built, do so."""
        return build("youtube", "v3", developerKey=self.api_key)


class Video(Youtube):
    """Connect to and get info from google API about a youtube video."""

    def __init__(self, video_id: str, api_key: str) -> None:
        """Construct a Video class object, a subclass of Youtube.

        Attributes
        ----------
        video_id : str
            The ID for a youtube video
        api_key : str
            The user's google api client key

        """
        self.video_id = video_id
        super().__init__(api_key)

    @cached_property
    def comment_threads(self) -> list[str]:
        """The list of comment thread ids for this video."""
        request = self.api.commentThreads().list(
            part="id",
            videoId=self.video_id,
            maxResults=100,
        )
        comment_threads = []

        while request:
            try:
                response = request.execute()

                for item in response["items"]:
                    if item["kind"] == "youtube#commentThread":
                        comment_threads.append(item["id"])
                request = self.api.commentThreads().list_next(request, response)
            except Exception as e:
                print(str(e))
                print(traceback.format_exc())
                break
        sleep(1)  # nap to avoid breaking the api
        return comment_threads

    def fetch_comments(self) -> pl.DataFrame:
        """Fetch all the comments for the given video.

        _fetch_comment_batch does the heavy lifting, this just iterates over the
        comment_threads for the video.
        """
        df = pl.DataFrame(
            schema={
                "comment": str,
                "comment_dt": str,
                "user_name": str,
                "like_cnt": str,
                "reply_cnt": str,
                "replies": list[str],
            }
        )

        for i in range(0, len(self.comment_threads), 50):
            comment_batch = self.comment_threads[i : i + 50]
            df2 = self._fetch_comment_batch(comment_batch)
            sleep(1)  # nap to avoid breaking the api
            df = pl.concat([df, df2])

        return df

    def _fetch_comment_batch(self, comment_batch: list[str]) -> pl.DataFrame:
        """Goes and gets info for this batch of comments.

        Parameters
        ----------
        comment_batch : list[str]
            The commentThread ids to pull in this batch

        Returns
        -------
        pl.DataFrame

        """
        comments: list[str] = []
        comment_dts: list[str] = []
        user_names: list[str] = []
        like_cnts: list[str] = []
        reply_cnts: list[str] = []
        replies: list[list[str]] = []

        comment_ids = ",".join(comment_batch)

        request = self.api.commentThreads().list(
            part="snippet,replies",
            id=comment_ids,
            maxResults=50,
        )
        response = request.execute()

        for item in response["items"]:
            top_comment = item["snippet"]["topLevelComment"]["snippet"]

            comment = top_comment["textDisplay"]
            comments.append(comment)

            comment_dt = top_comment["publishedAt"]
            comment_dts.append(comment_dt)

            user_name = top_comment["authorDisplayName"]
            user_names.append(user_name)

            like_cnt = top_comment["likeCount"]
            like_cnts.append(str(like_cnt))

            reply_cnt = item["snippet"]["totalReplyCount"]
            reply_cnts.append(str(reply_cnt))

            if reply_cnt > 0:
                # start with an empyty list
                replies.append([])
                for reply in item["replies"]["comments"]:
                    # extract the reply text
                    reply = reply["snippet"]["textDisplay"]
                    # append to the last item in the replies list
                    replies[-1].append(reply)
            else:
                replies.append([])

        df = pl.DataFrame(
            data={
                "comment": comments,
                "comment_dt": comment_dts,
                "user_name": user_names,
                "like_cnt": like_cnts,
                "reply_cnt": reply_cnts,
                "replies": replies,
            }
        )
        return df


class Channel(Youtube):
    """Connect to and get info from google API about a youtube channel.

    Notes
    -----
    _fetch_video_batch(video_batch):
        A secret method to do the heavy lifting to retrieve the videos.

    Properties
    ----------
    channel_id : str
        The long-format, immutable id for a given Youtube channel.
        Fetched from the channels api based on the class channel_handle
    uploads_id : str
        The id for the channels "uploads" playlist.
        This is an auto-generated playlist that contains all uploads for a channel
        Fetched from the channels api based on the class channel_handle
    video_ids : list[str]
        The id for all of the videos in the channels "uploads" playlist.
        This should be all videos publically associated with a channel
        There's a chance that a user could remove a video from their uploads playlist

    Methods
    -------
    fetch_videos()
        Fetch a dataframe with basic stats for all videos for this channel
    fetch_comments(video_id)
        Fetch a dataframe with all the comments for a video on this channel

    """

    def __init__(self, channel_handle: str, api_key: str) -> None:
        """Construct a Channel class object, a subclass of Youtube.

        Attributes
        ----------
        channel_handle : str
            The name of the channel as displayed in the channel URL, eg "@LylaMev"
        api_key : str
            The user's googleapiclient API key. Keep it secret, keep it safe

        """
        self.channel_handle = channel_handle
        super().__init__(api_key)

    @cached_property
    def channel_id(self) -> str:
        """If the channel ID hasn't been fetched from the api, do so.

        Calls the channels resource, list request, filtering by channel_handle to get
        the channel_id from the first item in the items list. We're going to assume that
        only one channel exists per handle and throw an error if there's two.
        """
        request = self.api.channels().list(
            part="id,contentDetails",
            forHandle=self.channel_handle,
        )
        response = request.execute()

        if len(response["items"]) > 1:
            raise RuntimeError("More than one response received, handle is ambiguous")
        sleep(1)  # nap to avoid flooding the API
        return response["items"][0]["id"]

    @cached_property
    def uploads_id(self) -> str:
        """If the playlist ID for the 'uploads' playlist hasn't been fetched, do so.

        Calls the channels resource, list request, filtering by channel_handle to get
        the "uploads" playlist id from the "relatedPlaylists" contendDetails. We're
        going to assume that only one channel exists per handle and throw an error if
        there's two.
        """
        request = self.api.channels().list(
            part="id,contentDetails", forHandle=self.channel_handle
        )
        response = request.execute()

        if len(response["items"]) > 1:
            raise RuntimeError("More than one response received, channel id ambiguous")
        sleep(1)
        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    @cached_property
    def video_ids(self) -> list[str]:
        """If all the video IDs for this channel haven't been fetched, do so.

        Calls the playlistItems resource, list request, filtering by uploads_id to get
        all the video ids for the "uploads" playlist for our youtube channel. We
        iterate over the response to build a list of video ids associated with our
        channel.
        """
        request = self.api.playlistItems().list(
            part="snippet",
            playlistId=self.uploads_id,
            maxResults=50,
        )
        video_ids = []
        while request:
            try:
                response = request.execute()

                for item in response["items"]:
                    resource = item["snippet"]["resourceId"]
                    if resource["kind"] == "youtube#video":
                        video_id = resource["videoId"]
                        video_ids.append(video_id)
                request = self.api.playlistItems().list_next(request, response)
                sleep(1)  # nap to avoid breaking the api
            except Exception as e:
                print(str(e))
                print(traceback.format_exc())
                break
        return video_ids

    def fetch_videos(self) -> pl.DataFrame:
        """Fetch a dataframe with basic stats for all videos for this channel.

        _fetch_video_batch does the heavy lifting, this just iterates through all of
        the video ids.

        Returns
        -------
        pl.DataFrame
            The stats for all of the videos associated with this channel

        """
        df = pl.DataFrame(
            schema={
                "video_id": str,
                "published_dt": str,
                "video_title": str,
                "video_description": str,
                "video_tags": list[str],
                "view_cnt": str,
                "like_cnt": str,
                "fave_cnt": str,
                "comment_cnt": str,
            }
        )
        # Batch videos 50 at a time
        for i in range(0, len(self.video_ids), 50):
            video_batch = self.video_ids[i : i + 50]
            df2 = self._fetch_video_batch(video_batch)
            sleep(1)  # nap to avoid breaking the api
            df = pl.concat([df, df2])

        return df

    def _fetch_video_batch(self, video_batch: list[str]) -> pl.DataFrame:
        """Fetch a batch of up to 50 results at a time.

        Make iterating so much easier.

        Parameters
        ----------
        video_batch : list[str]
            A batch of up to 50 video ids to look up

        Returns
        -------
        pl.DataFrame
            A dataframe with a batch of video results

        """
        video_ids = ",".join(video_batch)
        request = self.api.videos().list(
            part="id,snippet,statistics",
            id=video_ids,
            maxResults=50,
        )
        response = request.execute()

        video_ids: list[str] = []
        published_dts: list[str] = []
        video_titles: list[str] = []
        video_descriptions: list[str] = []
        video_tags: list[list[str]] = []
        view_cnts: list[str] = []
        like_cnts: list[str] = []
        fave_cnts: list[str] = []
        comment_cnts: list[str] = []

        for item in response["items"]:
            if item["kind"] == "youtube#video":
                # Extract the info
                video_id = item["id"]
                video_ids.append(video_id)

                snippet = item["snippet"]

                published_dt = snippet["publishedAt"]
                published_dts.append(published_dt)

                video_title = snippet["title"]
                video_titles.append(video_title)

                video_description = snippet["description"]
                video_descriptions.append(video_description)

                video_tag = snippet["tags"]
                video_tags.append(video_tag)

                stats = item["statistics"]

                view_cnt = stats["viewCount"]
                view_cnts.append(view_cnt)

                like_cnt = stats["likeCount"]
                like_cnts.append(like_cnt)

                fave_cnt = stats["favoriteCount"]
                fave_cnts.append(fave_cnt)

                comment_cnt = stats["commentCount"]
                comment_cnts.append(comment_cnt)
        df = pl.DataFrame(
            data={
                "video_id": video_ids,
                "published_dt": published_dts,
                "video_title": video_titles,
                "video_description": video_descriptions,
                "video_tags": video_tags,
                "view_cnt": view_cnts,
                "like_cnt": like_cnts,
                "fave_cnt": fave_cnts,
                "comment_cnt": comment_cnts,
            }
        )

        return df

"""Packages for performing Youtube sentiment analysis.

This project will read in some data from Google's client APIs and create some datasets for performing sentiment
analysis, then perform sentiment analysis on the comments for some videos. The goal is to determine if some
Youtube content creators in the Warhammer 40k/miniature painting space attract more negative comments than others
(in particular, do female creators fare worse than male creators).

Classes
-------
Youtube
    A base class, not used by itself. Sets up API.
Video
    A class representing a single Youtube video. Has methods to extract comments for analysis.
Channel
    A class representing a Youtube channel. Has methods to extract channel and video stats for analysis.
"""

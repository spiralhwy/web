// .eleventy.js
module.exports = function(eleventyConfig) {

  // keep saved test fixtures (copies of theater websites) out of the published site
  eleventyConfig.ignores.add("spiral_hwy/tests/**");

  // copy into public
  eleventyConfig.addPassthroughCopy({ "spiral_hwy/fonts": "fonts" });
  eleventyConfig.addPassthroughCopy({ "spiral_hwy/css/styles.css": "styles.css" });

  // format date string
  // need to replace dashes with slashes for correct evaluation
  eleventyConfig.addFilter("formatDate", function(dateString) {
    const date = new Date(dateString.replace(/-/g, '\/'));
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      day: 'numeric',
      month: 'long'
    });
  });

  // format time
  eleventyConfig.addFilter("formatTime", function(timeString) {
    const hours = parseInt(timeString.substring(0, 2));
    const minutes = timeString.substring(2);
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    return `${displayHours}:${minutes} ${period}`;
  });

  // format a theater slug for display (e.g. "alamo_drafthouse_sf" -> "Alamo Drafthouse SF")
  // title-cases each word, but keeps known acronyms fully capitalized
  // and short connecting words lowercase ("bottom_of_the_hill" -> "Bottom of the Hill")
  const UPPERCASE_WORDS = new Set(["sf"]);
  const LOWERCASE_WORDS = new Set(["of", "the", "and"]);
  eleventyConfig.addFilter("displayName", function(slug) {
    return String(slug).split("_").map(function(word, i) {
      const lower = word.toLowerCase();
      if (UPPERCASE_WORDS.has(lower)) return lower.toUpperCase();
      if (i > 0 && LOWERCASE_WORDS.has(lower)) return lower;
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    }).join(" ");
  });

  // site-wide values used for SEO metadata, robots.txt, and sitemap.xml
  eleventyConfig.addGlobalData("site", {
    url: "https://www.spiralhwy.com",
    buildDate: new Date().toISOString().slice(0, 10),
    // UTC "YYYYMMDDTHHMMSSZ", for iCalendar DTSTAMP
    buildTimestamp: new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z",
  });

  // collect the unique theaters across all listings, sorted by slug
  eleventyConfig.addFilter("uniqueTheaters", function(movies) {
    const theaters = new Map();
    (movies || []).forEach(function(day) {
      day.movies.forEach(function(movie) {
        movie.listings.forEach(function(listing) {
          if (!theaters.has(listing.theater)) {
            theaters.set(listing.theater, listing);
          }
        });
      });
    });
    return Array.from(theaters.values()).sort(function(a, b) {
      return a.theater.localeCompare(b.theater);
    });
  });

  // pull one field out of each item (e.g. movies | pluck("date"))
  eleventyConfig.addFilter("pluck", function(items, key) {
    return (items || []).map(function(item) { return item[key]; });
  });

  // collect the unique music venues across all events, sorted by slug
  eleventyConfig.addFilter("uniqueVenues", function(music) {
    const venues = new Map();
    (music || []).forEach(function(day) {
      day.events.forEach(function(event) {
        if (!venues.has(event.venue)) {
          venues.set(event.venue, event);
        }
      });
    });
    return Array.from(venues.values()).sort(function(a, b) {
      return a.venue.localeCompare(b.venue);
    });
  });

  // iCalendar (RFC 5545) helpers for music.ics
  // escape a TEXT value: backslash, semicolon, comma, and newlines
  eleventyConfig.addFilter("icsText", function(text) {
    return String(text || "")
      .replace(/\\/g, "\\\\")
      .replace(/;/g, "\\;")
      .replace(/,/g, "\\,")
      .replace(/\r?\n/g, "\\n");
  });

  // "2026-10-28" + "2000" -> "20261028T200000" (local time; pair with TZID)
  eleventyConfig.addFilter("icsDateTime", function(dateString, timeString) {
    return dateString.replace(/-/g, "") + "T" + timeString + "00";
  });

  // .ics files need CRLF line endings and lines folded at 75 octets
  eleventyConfig.addTransform("ics", function(content) {
    if (!(this.page.outputPath || "").endsWith(".ics")) return content;
    const encoder = new TextEncoder();
    return content.split(/\r?\n/).filter(function(line) {
      return line.trim() !== "";
    }).map(function(line) {
      const folded = [];
      let current = "";
      for (const ch of line) {
        // continuation lines start with a space, which counts toward the limit
        const limit = folded.length === 0 ? 75 : 74;
        if (encoder.encode(current + ch).length > limit) {
          folded.push(current);
          current = "";
        }
        current += ch;
      }
      folded.push(current);
      return folded.join("\r\n ");
    }).join("\r\n") + "\r\n";
  });

  return {
    dir: {
      input: "spiral_hwy",
      output: "public",
    }
  };
};

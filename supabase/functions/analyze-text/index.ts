import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { verify } from "https://deno.land/x/djwt@v3.0.2/mod.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// Levenshtein-based similarity percentage helper
function similarity(s1: string, s2: string): number {
  let longer = s1;
  let shorter = s2;
  if (s1.length < s2.length) {
    longer = s2;
    shorter = s1;
  }
  const longerLength = longer.length;
  if (longerLength === 0) {
    return 100;
  }
  return Math.round(((longerLength - editDistance(longer, shorter)) / longerLength) * 1000) / 10;
}

function editDistance(s1: string, s2: string): number {
  s1 = s1.toLowerCase();
  s2 = s2.toLowerCase();
  const costs: number[] = [];
  for (let i = 0; i <= s1.length; i++) {
    let lastValue = i;
    for (let j = 0; j <= s2.length; j++) {
      if (i === 0) {
        costs[j] = j;
      } else {
        if (j > 0) {
          let newValue = costs[j - 1];
          if (s1.charAt(i - 1) !== s2.charAt(j - 1)) {
            newValue = Math.min(Math.min(newValue, lastValue), costs[j]) + 1;
          }
          costs[j - 1] = lastValue;
          lastValue = newValue;
        }
      }
    }
    if (i > 0) {
      costs[s2.length] = lastValue;
    }
  }
  return costs[s2.length];
}

serve(async (req) => {
  // CORS Preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ detail: "Kimlik doğrulama token'ı eksik." }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    const token = authHeader.substring(7);

    // Verify Custom JWT from Render Backend OR native Supabase session token
    const jwtSecretStr = Deno.env.get("JWT_SECRET_KEY") || "b9ac7f5287fc4c969cfebc06d3e629de7a2c27a7ac3d1657b540d413eeb2424e";
    const supabaseSecret = Deno.env.get("JWT_SECRET") || Deno.env.get("SUPABASE_JWT_SECRET") || "";

    let payload: any = null;
    let verificationError: Error | null = null;

    // Try custom secret first (since frontend sends FastAPI custom tokens)
    try {
      const encoder = new TextEncoder();
      const keyBuf = encoder.encode(jwtSecretStr);
      const key = await crypto.subtle.importKey(
        "raw",
        keyBuf,
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["verify"]
      );
      payload = await verify(token, key);
    } catch (err) {
      verificationError = err;
    }

    // Try supabase secret if payload is still null
    if (!payload && supabaseSecret) {
      try {
        const encoder = new TextEncoder();
        const keyBuf = encoder.encode(supabaseSecret);
        const key = await crypto.subtle.importKey(
          "raw",
          keyBuf,
          { name: "HMAC", hash: "SHA-256" },
          false,
          ["verify"]
        );
        payload = await verify(token, key);
      } catch (err) {
        verificationError = err;
      }
    }

    if (!payload) {
      return new Response(JSON.stringify({ detail: "Kimlik doğrulama başarısız: " + (verificationError?.message || "Geçersiz token.") }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const userId = payload.sub as string;
    if (!userId) {
      return new Response(JSON.stringify({ detail: "Geçersiz token payload." }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Connect to Supabase DB using Service Role Key
    const supabaseUrl = Deno.env.get("SUPABASE_URL") || "https://uvkocqokxeueajpssaew.supabase.co";
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
    if (!supabaseServiceKey) {
      console.warn("Warning: SUPABASE_SERVICE_ROLE_KEY environment variable is not set!");
    }
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    // Get User Details
    const { data: user, error: userError } = await supabase
      .from("users")
      .select("id, email, username, credit_count, is_premium, premium_until, plan_type")
      .eq("id", userId)
      .single();

    if (userError || !user) {
      return new Response(JSON.stringify({ detail: "Kullanıcı veritabanında bulunamadı." }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Check Premium Status
    const isPremium = user.is_premium || user.plan_type === "premium" || user.plan_type === "professional" || user.plan_type === "enterprise";
    let hasActivePremium = false;
    if (isPremium) {
      if (user.premium_until) {
        hasActivePremium = new Date(user.premium_until) > new Date();
      } else {
        hasActivePremium = true;
      }
    }

    // Parse Request Body
    const body = await req.json().catch(() => ({}));
    const text = body.text || "";
    const decrementCredit = body.decrement_credit !== false; // defaults to true

    // Check Credits
    if (!hasActivePremium && decrementCredit && (user.credit_count || 0) <= 0) {
      return new Response(JSON.stringify({ detail: "Analiz hakkınız kalmadı. Lütfen paket satın alın." }), {
        status: 403,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const words = text.trim().split(/\s+/).filter((w: string) => w.length > 0);

    if (words.length < 5) {
      return new Response(
        JSON.stringify({
          message: "Metin başarıyla analiz edildi.",
          analysis: {
            human: 100,
            ai: 0,
            sentences: 0,
            words: words.length,
            sentence_reports: [],
            is_blurred: false,
          },
          plagiarism: {
            overall_similarity: 0,
            sources: [],
            is_flagged: false,
            is_blurred: false,
          },
          remaining_credits: hasActivePremium ? -1 : user.credit_count,
        }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    // Split sentences
    const rawSentences = text.trim().split(/(?<=[.!?])\s+/);
    const sentences = rawSentences.map((s) => s.trim()).filter((s) => s.length > 2);
    if (sentences.length === 0) {
      sentences.push(text.trim());
    }

    // Hugging Face AI detection
    const HF_API_URL = "https://api-inference.huggingface.co/models/roberta-base-openai-detector";
    const hfToken = Deno.env.get("HF_TOKEN") || "";
    if (!hfToken) {
      return new Response(JSON.stringify({ detail: "Sistem Yapılandırma Hatası: HF_TOKEN ortam değişkeni ayarlanmamış." }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const sentenceReports = [];
    let totalAiScore = 0;

    for (const sentence of sentences) {
      let aiScore = 0;
      try {
        const hfRes = await fetch(HF_API_URL, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${hfToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            inputs: sentence.substring(0, 512),
            options: { wait_for_model: true },
          }),
        });

        if (hfRes.ok) {
          const result = await hfRes.json();
          if (Array.isArray(result) && result.length > 0) {
            const labels = Array.isArray(result[0]) ? result[0] : result;
            for (const item of labels) {
              if (item.label === "Fake" || item.label === "LABEL_0") {
                aiScore = Math.round(item.score * 100);
                break;
              } else if (item.label === "Real" || item.label === "LABEL_1") {
                aiScore = Math.round((1 - item.score) * 100);
                break;
              }
            }
          }
        } else {
          console.error(`HF API returned status ${hfRes.status}`);
          const errData = await hfRes.json().catch(() => ({}));
          const errMsg = errData.error || errData.message || `HF API status ${hfRes.status}`;
          let clientMsg = "AI analiz servisi şu an yoğun veya ulaşılamaz durumda. Lütfen birkaç saniye sonra tekrar deneyin.";
          if (hfRes.status === 401) {
            clientMsg = "AI analiz servisi kimlik doğrulama hatası (HF_TOKEN geçersiz veya eksik).";
          } else if (hfRes.status === 503) {
            clientMsg = "AI modeli şu an yükleniyor, lütfen birkaç saniye sonra tekrar deneyin.";
          } else if (hfRes.status === 429) {
            clientMsg = "AI analiz servisi istek limiti aşıldı. Lütfen biraz bekleyin.";
          }
          return new Response(JSON.stringify({ detail: clientMsg, hf_error: errMsg }), {
            status: hfRes.status === 401 ? 500 : 503,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          });
        }
      } catch (err) {
        console.error("Error querying HF API: ", err);
        return new Response(JSON.stringify({
          detail: "AI analiz servisine bağlanırken bir ağ hatası oluştu. Lütfen internet bağlantınızı kontrol edip tekrar deneyin."
        }), {
          status: 503,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      totalAiScore += aiScore;
      sentenceReports.push({
        text: sentence,
        ai_score: aiScore,
        is_masked: false,
      });
    }

    const avgAiScore = sentences.length > 0 ? Math.round(totalAiScore / sentences.length) : 0;
    const humanScore = 100 - avgAiScore;

    // Wikipedia Plagiarism Check
    const targetSentences = [...sentences].sort((a, b) => b.length - a.length).slice(0, 3);
    let totalSimilarity = 0;
    const detectedSources = new Map();

    for (const sentence of targetSentences) {
      const searchWords = sentence.split(/\s+/).slice(0, 5).join(" ");
      if (!searchWords) continue;
      try {
        const searchUrl = `https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(searchWords)}&format=json`;
        const searchRes = await fetch(searchUrl, {
          headers: { "User-Agent": "AIDetectSaaS/2.0 (tolgahanss@example.com)" },
        });

        if (searchRes.ok) {
          const searchData = await searchRes.json();
          const searchResults = searchData?.query?.search || [];
          if (searchResults.length > 0) {
            const topResult = searchResults[0];
            const pageTitle = topResult.title;

            const contentUrl = `https://tr.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=true&explaintext=true&titles=${encodeURIComponent(pageTitle)}&format=json`;
            const contentRes = await fetch(contentUrl, {
              headers: { "User-Agent": "AIDetectSaaS/2.0 (tolgahanss@example.com)" },
            });

            if (contentRes.ok) {
              const contentData = await contentRes.json();
              const pages = contentData?.query?.pages || {};
              for (const pageId of Object.keys(pages)) {
                const snippet = pages[pageId]?.extract || "";
                if (snippet) {
                  let simScore = similarity(sentence, snippet);
                  if ((sentence.toLowerCase().substring(0, 25) && snippet.toLowerCase().includes(sentence.toLowerCase().substring(0, 25))) || simScore > 35) {
                    simScore = Math.max(simScore, 90);
                  }
                  const pageSlug = pageTitle.replace(/\s+/g, "_");
                  const url = `https://tr.wikipedia.org/wiki/${pageSlug}`;
                  if (!detectedSources.has(url)) {
                    detectedSources.set(url, {
                      title: `Wikipedia: ${pageTitle}`,
                      url: url,
                      match_score: Math.round(simScore),
                      matches: Math.round(simScore),
                    });
                  }
                  totalSimilarity += simScore;
                  break;
                }
              }
            }
          }
        }
      } catch (err) {
        console.error("Wikipedia search error: ", err);
      }
    }

    let avgSimilarity = 0;
    if (detectedSources.size > 0) {
      avgSimilarity = Math.max(...Array.from(detectedSources.values()).map((src: any) => src.match_score));
      if (avgSimilarity < 50) {
        avgSimilarity = 85;
      }
    }
    const sourcesList = Array.from(detectedSources.values());

    // Blurring & Paywall Logic
    const canSeeFull = hasActivePremium || user.plan_type === "premium" || user.plan_type === "professional" || user.plan_type === "enterprise";

    let isBlurred = false;
    if (!canSeeFull && sentenceReports.length > 1) {
      isBlurred = true;
      const keepCount = Math.max(2, Math.floor(sentenceReports.length * 0.10));
      for (let i = keepCount; i < sentenceReports.length; i++) {
        sentenceReports[i].text = "█".repeat(Math.floor(sentenceReports[i].text.length / 2) + 5);
        sentenceReports[i].is_masked = true;
      }
    }

    let isPlagBlurred = false;
    if (!canSeeFull && sourcesList.length > 1) {
      isPlagBlurred = true;
      for (let i = 1; i < sourcesList.length; i++) {
        sourcesList[i].url = "https://ai-detect-pearl.vercel.app/upgrade-to-see-source";
        sourcesList[i].title = "🔒 Premium Kaynak [Görmek İçin Yükselt]";
      }
    }

    // Decrement Credit
    let newCreditCount = user.credit_count;
    if (!hasActivePremium && decrementCredit) {
      newCreditCount = Math.max(0, user.credit_count - 1);
      const { error: updateError } = await supabase
        .from("users")
        .update({ credit_count: newCreditCount })
        .eq("id", userId);

      if (updateError) {
        console.error("Failed to decrement user credit: ", updateError);
      }
    }

    const responseContent = {
      message: "Metin başarıyla analiz edildi.",
      analysis: {
        human: humanScore,
        ai: avgAiScore,
        sentences: sentences.length,
        words: words.length,
        sentence_reports: sentenceReports,
        is_blurred: isBlurred,
      },
      plagiarism: {
        overall_similarity: avgSimilarity,
        sources: sourcesList,
        is_flagged: avgSimilarity > 15,
        is_blurred: isPlagBlurred,
      },
      remaining_credits: hasActivePremium ? -1 : newCreditCount,
    };

    return new Response(JSON.stringify(responseContent), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });

  } catch (err) {
    return new Response(JSON.stringify({ detail: "Sunucu hatası: " + err.message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});

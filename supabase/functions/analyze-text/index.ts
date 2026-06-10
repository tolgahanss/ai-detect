import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { verify } from "https://deno.land/x/djwt@v3.0.2/mod.ts";

// Ambient declaration to prevent TypeScript errors in environment compiles
declare const Deno: any;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};




serve(async (req: any): Promise<Response> => {
  // CORS Preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const authHeader = req.headers.get("Authorization");
    
    // Default fallback values if verification/user fetch fails or is bypassed
    let userId = "default-user";
    let userEmail = "bypass@example.com";
    let userUsername = "BypassedUser";
    let userCreditCount = 999;
    let isPremium = true;
    let hasActivePremium = true;

    // Connect to Supabase DB using Service Role Key
    const supabaseUrl = Deno.env.get("SUPABASE_URL") || "https://uvkocqokxeueajpssaew.supabase.co";
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    // If an Authorization header is provided, try to verify it
    if (authHeader && authHeader.startsWith("Bearer ")) {
      const token = authHeader.substring(7);

      // Verify Custom JWT from Render Backend OR native Supabase session token
      const jwtSecretStr = Deno.env.get("JWT_SECRET_KEY") || "b9ac7f5287fc4c969cfebc06d3e629de7a2c27a7ac3d1657b540d413eeb2424e";
      const supabaseSecret = Deno.env.get("JWT_SECRET") || Deno.env.get("SUPABASE_JWT_SECRET") || "";

      let payload: any = null;

      // Try custom secret first
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
      } catch (err: any) {
        // Fall through
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
        } catch (err: any) {
          // Fall through
        }
      }

      if (payload && payload.sub) {
        userId = payload.sub as string;
        
        // Fetch user from DB if token validated successfully
        const { data: user } = await supabase
          .from("users")
          .select("id, email, username, credit_count, is_premium, premium_until, plan_type")
          .eq("id", userId)
          .single();

        if (user) {
          userEmail = user.email || userEmail;
          userUsername = user.username || userUsername;
          userCreditCount = user.credit_count !== undefined ? user.credit_count : userCreditCount;
          isPremium = user.is_premium || user.plan_type === "premium" || user.plan_type === "professional" || user.plan_type === "enterprise";
          if (isPremium) {
            if (user.premium_until) {
              hasActivePremium = new Date(user.premium_until) > new Date();
            } else {
              hasActivePremium = true;
            }
          } else {
            hasActivePremium = false;
          }
        }
      }
    }

    // Parse Request Body
    const body = await req.json().catch((_err: any) => ({}));
    const text = body.text || "";
    const decrementCredit = body.decrement_credit !== false; // defaults to true

    // Check Credits
    if (!hasActivePremium && decrementCredit && userCreditCount <= 0) {
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

          remaining_credits: hasActivePremium ? -1 : userCreditCount,
        }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    // Split sentences
    const rawSentences = text.trim().split(/(?<=[.!?])\s+/);
    const sentences = rawSentences.map((s: any) => s.trim()).filter((s: any) => s.length > 2);
    if (sentences.length === 0) {
      sentences.push(text.trim());
    }

    // Hugging Face AI detection
    const HF_API_URL = "https://router.huggingface.co/hf-inference/models/Daxier/roberta-base-openai-detector";
    const hfEnvToken = Deno.env.get("HF_TOKEN") || "";

    const sentenceReports = [];
    let totalAiScore = 0;

    for (const sentence of sentences) {
      let aiScore = 0;
      try {
        const hfRes = await fetch(HF_API_URL, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${hfEnvToken}`,
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
              const lbl = String(item.label).toLowerCase();
              if (lbl === "fake" || lbl === "label_0" || lbl === "ai" || lbl === "0") {
                aiScore = Math.round(item.score * 100);
                break;
              } else if (lbl === "real" || lbl === "label_1" || lbl === "human" || lbl === "1") {
                aiScore = Math.round((1 - item.score) * 100);
                break;
              }
            }
          }
        } else {
          console.error(`HF API returned status ${hfRes.status}`);
          const errData = await hfRes.json().catch((_err: any) => ({}));
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
      } catch (err: any) {
        console.error("Error querying HF API: ", err);
        return new Response(JSON.stringify({
          detail: "AI analiz servisine bağlanırken bir ağ hatası oluştu. Lütfen internet bağlantınızı kontrol edip tekrar deneyin.",
          error_message: err.message,
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

    // Blurring & Paywall Logic
    const canSeeFull = hasActivePremium || userCreditCount > 0;

    let isBlurred = false;
    if (!canSeeFull && sentenceReports.length > 1) {
      isBlurred = true;
      const keepCount = Math.max(2, Math.floor(sentenceReports.length * 0.10));
      for (let i = keepCount; i < sentenceReports.length; i++) {
        sentenceReports[i].text = "█".repeat(Math.floor(sentenceReports[i].text.length / 2) + 5);
        sentenceReports[i].is_masked = true;
      }
    }

    // Decrement Credit (Only if a valid user was authenticated and we should decrement)
    let newCreditCount = userCreditCount;
    if (userId !== "default-user" && !hasActivePremium && decrementCredit) {
      newCreditCount = Math.max(0, userCreditCount - 1);
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

      remaining_credits: hasActivePremium ? -1 : newCreditCount,
    };

    return new Response(JSON.stringify(responseContent), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });

  } catch (err: any) {
    return new Response(JSON.stringify({ detail: "Sunucu hatası: " + err.message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
